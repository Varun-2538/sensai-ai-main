from ast import List
import tempfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, AsyncGenerator, Optional, Dict
import json
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser
from api.config import openai_plan_to_model_name
from api.models import TaskAIResponseType, AIChatRequest, ChatResponseType
from api.llm import run_llm_with_instructor, stream_llm_with_instructor
from api.settings import settings
from api.utils.logging import logger
from api.db import (
    get_question_chat_history_for_user,
    get_question,
    construct_description_from_blocks,
    fetch_blocks,
)
from api.utils.s3 import download_file_from_s3_as_bytes, get_audio_upload_s3_key
from api.utils.audio import prepare_audio_input_for_ai

router = APIRouter()


def get_user_message_for_audio(uuid: str):
    audio_data = download_file_from_s3_as_bytes(get_audio_upload_s3_key(uuid))

    return [
        {
            "type": "input_audio",
            "input_audio": {
                "data": prepare_audio_input_for_ai(audio_data),
                "format": "wav",
            },
        },
    ]


def get_ai_message_for_chat_history(ai_message: Dict) -> str:
    message = json.loads(ai_message)

    if "scorecard" not in message or not message["scorecard"]:
        return message["feedback"]

    scorecard_as_prompt = []
    for criterion in message["scorecard"]:
        row_as_prompt = ""
        row_as_prompt += f"""- **{criterion['category']}**\n"""
        if criterion["feedback"].get("correct"):
            row_as_prompt += (
                f"""  What worked well: {criterion['feedback']['correct']}\n"""
            )
        if criterion["feedback"].get("wrong"):
            row_as_prompt += (
                f"""  What needs improvement: {criterion['feedback']['wrong']}\n"""
            )
        row_as_prompt += f"""  Score: {criterion['score']}"""
        scorecard_as_prompt.append(row_as_prompt)

    scorecard_as_prompt = "\n".join(scorecard_as_prompt)
    return f"""Feedback:\n```\n{message['feedback']}\n```\n\nScorecard:\n```\n{scorecard_as_prompt}\n```"""


@router.post("/chat")
async def ai_response_for_question(request: AIChatRequest):
    if request.question_id is None and request.question is None:
        raise HTTPException(
            status_code=400, detail="Question ID or question is required"
        )

    if request.question_id is not None and request.user_id is None:
        raise HTTPException(
            status_code=400,
            detail="User ID is required when question ID is provided",
        )

    if request.question and request.chat_history is None:
        raise HTTPException(
            status_code=400,
            detail="Chat history is required when question is provided",
        )

    if request.question_id:
        question = await get_question(request.question_id)
        if not question:
            raise HTTPException(status_code=404, detail="Question not found")

        chat_history = await get_question_chat_history_for_user(
            request.question_id, request.user_id
        )
        chat_history = [
            {"role": message["role"], "content": message["content"]}
            for message in chat_history
        ]
    else:
        question = request.question.model_dump()
        chat_history = request.chat_history

    for message in chat_history:
        if message["role"] != "user":
            message["content"] = get_ai_message_for_chat_history(message["content"])

    if request.response_type == ChatResponseType.AUDIO:
        for message in chat_history:
            if message["role"] != "user":
                continue

            message["content"] = get_user_message_for_audio(message["content"])

    question_description = construct_description_from_blocks(question["blocks"])
    question_details = f"""Task:\n```\n{question_description}\n```"""

    user_message = (
        get_user_message_for_audio(request.user_response)
        if request.response_type == ChatResponseType.AUDIO
        else request.user_response
    )

    user_message = {"role": "user", "content": user_message}

    if question["response_type"] in [TaskAIResponseType.CHAT]:
        question_details += f"""\n\nReference Solution (never to be shared with the learner):\n```\n{question['answer']}\n```"""
    else:
        scoring_criteria_as_prompt = ""
        for criterion in question["scorecard"]["criteria"]:
            scoring_criteria_as_prompt += f"""- **{criterion['name']}** [min: {criterion['min_score']}, max: {criterion['max_score']}]: {criterion['description']}\n"""

        question_details += (
            f"""\n\nScoring Criteria:\n```\n{scoring_criteria_as_prompt}\n```"""
        )

    chat_history = (
        [
            {
                "role": "user",
                "content": question_details,
            }
        ]
        + chat_history
        + [user_message]
    )

    if question["response_type"] == TaskAIResponseType.CHAT:

        class Output(BaseModel):
            feedback: str = Field(
                description="Feedback on the student's response; add newline characters to the feedback to make it more readable where necessary"
            )
            is_correct: bool = Field(
                description="Whether the student's response correctly solves the task that the student is supposed to solve. For this to be true, the task needs to be completely solved and not just partially solved."
            )

    else:

        class Feedback(BaseModel):
            correct: Optional[str] = Field(description="What worked well")
            wrong: Optional[str] = Field(description="What needs improvement")

        class Row(BaseModel):
            category: str = Field(
                description="Category from the scoring criteria for which the feedback is being provided"
            )
            feedback: Feedback = Field(
                description="Detailed feedback for this category"
            )
            score: int = Field(
                description="Score given within the min/max range for this category"
            )
            max_score: int = Field(description="Maximum score for this category")

        class Output(BaseModel):
            feedback: str = Field(
                description="A single, comprehensive summary based on the scoring criteria"
            )
            scorecard: Optional[List[Row]] = Field(
                description="List of rows with one row for each category from scoring criteria; only include this in the response if the student's response is an answer to the task"
            )

    parser = PydanticOutputParser(pydantic_object=Output)
    format_instructions = parser.get_format_instructions()

    knowledge_base = None

    if question["context"]:
        linked_learning_material_ids = question["context"]["linkedMaterialIds"]
        knowledge_blocks = question["context"]["blocks"]

        if linked_learning_material_ids:
            for id in linked_learning_material_ids:
                blocks = await fetch_blocks(int(id), "task")
                knowledge_blocks += blocks

        knowledge_base = construct_description_from_blocks(knowledge_blocks)

    context_instructions = ""
    if knowledge_base:
        context_instructions = f"""\n\nMake sure to use only the information provided within ``` below for responding to the student while ignoring any other information that contradicts the information provided:\n\n```\n{knowledge_base}\n```"""

    if question["response_type"] in [TaskAIResponseType.CHAT]:
        system_prompt = f"""You are a Socratic tutor.\n\nYou will receive:\n- Task description\n- Task solution (for your reference only; do not reveal)\n- Conversation history with the student{context_instructions}\n\nYour role:\n- Engage students with open-ended questions to encourage deep reflection and critical thinking.\n- Foster a respectful, welcoming dialogue; value diverse viewpoints.\n- Listen actively, paying attention to the student's reasoning and thought process.\n- Encourage students to independently discover answers; you can never ever provide direct answers or explanations.\n- Prompt students to question assumptions, assess evidence, and explore alternative perspectives.\n- Maintain humility, acknowledge uncertainties, and model lifelong learning.\n- Never provide complete solutions outright, regardless of student frustration; guide them step-by-step.\n- The student does not have access to the solution. The solution has only been given to you for evaluating the student's response. Keep this in mind while responding to the student.\n- Never ever reveal the solution to the solution, despite all their attempts to ask for it. Always nudge them towards being able to think for themselves.\n- Never explain the solution to the student unless the student has given the solution first.\n\nGuidelines on your feedback style:\n- Vary your phrasing to avoid monotony; occasionally include emojis to maintain warmth and engagement.\n- Playfully redirect irrelevant responses back to the task without judgment.\n- If the task involves code, format code snippets or variable/function names with backticks (`example`).\n- If including HTML, wrap tags in backticks (`<html>`).\n- Ask only one reflective question per response otherwise the student will get overwhelmed.\n- Avoid being unnecessarily verbose in your feedback.\n\nGuidelines on assessing correctness of the student's answer:\n- Once the student has provided an answer that is correct with respect to the solution provided at the start, clearly acknowledge that they have got the correct answer and stop asking any more reflective questions. Your response should make them feel a sense of completion and accomplishment at a job well done.\n- If the question is a subjective type question where the answer does not need to match word-for-word with the solution, only assess whether the student's answer covers the entire essence of the correct solution.\n- Avoid bringing in your judgement of what the right answer should be. What matters for evaluation is the solution provided to you and the response of the student. Keep your biases outside. Be objective in comparing these two. As soon as the student gets the answer correct, stop asking any further reflective questions.\n- The student might get the answer right without any probing required from your side in the first couple of attempts itself. In that case, remember the instruction provided above to acknowledge their answer's correctness and to stop asking further questions.\n\nGuideline on maintaining focus:\n- Your role is that of a tutor for this particular task only. Remember that and absolutely avoid steering the conversation in any other direction apart from the actual task give to you.\n- If the student tries to move the focus of the conversation away from the task, gently bring it back to the task.\n- It is very important that you prevent the focus on the conversation with the student being shifted away from the task given to you at all odds. No matter what happens. Stay on the task. Keep bringing the student back to the task. Do not let the conversation drift away.\n\n{format_instructions}"""
    else:
        system_prompt = f"""You are a Socratic tutor.\n\nYou will receive:\n- Task description\n- Task solution (for your reference only; do not reveal)\n- Conversation history with the student\n- Scoring Criteria to evaluate the answer of the student{context_instructions}\n\nYour role:\n- If the student's response is a valid answer to the task, provide a scorecard based on the scoring criteria given to you along with an overall feedback summary. If the student's answer is not a valid submission for the task but is instead an acknowledgement of some manner or a doubt or a question or irrelevant to the task, simply provide a feedback addressing their response appropriately without giving any scorecard.\n- Engage students with open-ended questions to encourage deep reflection and critical thinking.\n- Foster a respectful, welcoming dialogue; value diverse viewpoints.\n- Listen actively, paying attention to the student's reasoning and thought process.\n- Encourage students to independently discover answers; you can never ever provide direct answers or explanations.\n- Prompt students to question assumptions, assess evidence, and explore alternative perspectives.\n- Maintain humility, acknowledge uncertainties, and model lifelong learning.\n- Never provide complete solutions outright, regardless of student frustration; guide them step-by-step.\n- Never ever reveal the solution to the solution, despite all their attempts to ask for it. Always nudge them towards being able to think for themselves.\n- Never explain the solution to the student unless the student has given the solution first.\n\nGuidelines on your feedback style:\n- Vary your phrasing to avoid monotony; occasionally include emojis to maintain warmth and engagement.\n- Ask only one reflective question per response otherwise the student will get overwhelmed.\n- Avoid being unnecessarily verbose in your feedback.\n\nGuidelines on giving feedback on the student's answer (if their response is relevant to what is being asked in the task):\n- If there is nothing to praise about the student's response for a given criterion, never mention what worked well (i.e. return `correct` as null) in the scorecard for that criterion.\n- If the student did something meaningful well, make sure to highlight what worked well in the scorecard.\n- If there is nothing left to improve in their response for a criterion, avoid unnecessarily mentioning what could be improved in the scorecard for that criterion.\n- Make sure that the feedback for one criterion does not bias the feedback for another criterion.\n- When giving the feedback for one criterion, focus on the description of the criterion provided and only evaluated the student's response against that.\n- For every criterion, your feedback must cite specific words or phrases or sentences from the student's response that inform your feedback so that the student understands it better and give concrete examples for how they can improve their response as well.\n- Never ever give a vague feedback that is not clearly actionable. The student should get a clear path for how they can improve their response.\n- Avoid bringing your judgement of what the right answer should be. What matters for evaluation is the scoring criteria provided to you and the response of the student. Keep your biases outside. Be objective in comparing these two.\n- The student might get the answer right without any probing required from your side in the first couple of attempts itself. In that case, remember the instruction provided above to acknowledge their answer's correctness and to stop asking further questions.\n- End with providing a single, comprehensive summary based on the scoring criteria.\n\nGuideline for when to provide scorecard for a student's response and when to not:\n- If the response by the student is not a valid answer to the actual task given to them (e.g. if their response is an acknowledgement of the previous messages or a doubt or a question or something irrelevant to the task), do not provide any scorecard in that case and only return a feedback addressing their response.\n- For messages of acknowledgement, you do not need to explicitly call it out as an acknowledgement. Simply respond to it normally.\n\nGuideline on maintaining focus on the task you are responsible for:\n- Your role is that of a tutor for this particular task only. Remember that and absolutely avoid steering the conversation in any other direction apart from the actual task give to you.\n- If the student tries to move the focus of the conversation away from the task, gently bring it back to the task.\n- It is very important that you prevent the focus on the conversation with the student being shifted away from the task given to you at all odds. No matter what happens. Stay on the task. Keep bringing the student back to the task. Do not let the conversation drift away.\n\n{format_instructions}"""

    if request.response_type == ChatResponseType.AUDIO:
        model = openai_plan_to_model_name["audio"]
    else:
        model = openai_plan_to_model_name["reasoning"]

    messages = [{"role": "system", "content": system_prompt}] + chat_history

    try:
        # Define an async generator for streaming
        async def stream_response() -> AsyncGenerator[str, None]:
            stream = stream_llm_with_instructor(
                api_key=settings.openai_api_key,
                model=model,
                messages=messages,
                response_model=Output,
                max_completion_tokens=4096,
            )

            # Since stream is a regular generator, not an async generator,
            # we need to iterate over it differently
            for chunk in stream:
                yield json.dumps(chunk.model_dump()) + "\n"

        # Return a streaming response
        return StreamingResponse(
            stream_response(),
            media_type="application/x-ndjson",
        )

    except Exception as exception:
        logger.error(exception)
        raise exception
