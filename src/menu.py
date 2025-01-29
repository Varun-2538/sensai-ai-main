import streamlit as st
from typing import Dict
import os
from lib.organization import show_create_org_dialog
from lib.toast import set_toast, show_toast
from lib.db import get_hva_org_id

# if not theme:
#     theme = {"base": "light"}


def menu_header():
    if "theme" not in st.session_state or not st.session_state.theme:
        st.session_state.theme = {"base": "light"}

    if st.session_state.theme["base"] == "dark":
        st.logo("./lib/assets/dark_logo.svg")
        subtitle_color = "#fff"
    else:
        st.logo("./lib/assets/light_logo.svg")
        subtitle_color = "#1E2F4D"

    st.sidebar.markdown(
        f"""
        <p style='margin-top: -25px; margin-bottom: 15px; color: {subtitle_color}'>
        Your personal AI coach
        </p>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.page_link(
        "home.py",
        label="Home",
        icon="🏠",
    )


def show_links():
    with st.sidebar:
        st.page_link(
            "https://script.google.com/a/macros/hyperverge.co/s/AKfycbw-OKieiMdjBYp6qCMnF8J8iIusOkRN1xwA0Bamjn8C-ABHXGjfU6S6Km5xiZVViLvJ/exec",
            label="Apply for a leave",
            icon="🏖️",
        )
        st.page_link(
            "https://script.google.com/a/macros/hyperverge.co/s/AKfycbz14hcx16xpn5DklkSa_n28tfIVi8v9oXzDHYJVBBcTwZIDZZ3s6QpBD7WLEyPhKrxc/exec?page=interview_scheduling",
            label="Apply for a mock interview",
            icon="🎙️",
        )
        st.page_link(
            "https://chromewebstore.google.com/detail/sentence-enhancer/gomkfbbonafokpdagofhfkhoaeamcjmf?authuser=0&hl=en",
            label="Sentence Enhancer",
            icon="😎",
        )
        st.page_link(
            "https://wa.me/916366309432",
            label="Power Up (your English skills)",
            icon="🗣️",
        )


def clear_auth():
    st.experimental_user.logout()
    st.session_state.user = None
    st.session_state.email = None
    st.rerun()


def menu_footer(selected_cohort: Dict, role: str):
    st.sidebar.divider()

    if (
        role == "learner"
        and selected_cohort is not None
        and selected_cohort["org_id"] == get_hva_org_id()
    ):

        show_links()

        st.sidebar.divider()

    st.sidebar.page_link(
        "https://docs.sensai.hyperverge.org/",
        label="Product Guide",
        icon="📚",
    )

    st.sidebar.text("Built with ❤️ by HyperVerge Academy")

    if st.session_state.email:
        with st.sidebar.expander("More Options"):
            if st.button("Logout"):
                clear_auth()


def authenticated_menu(selected_cohort: Dict, role: str):
    with st.sidebar:
        st.page_link(
            f"{os.environ.get('APP_URL')}/profile",
            label="Your Profile",
            icon="👔",
        )

        if (
            role != "learner"
            or selected_cohort is None
            or selected_cohort["org_id"] != get_hva_org_id()
        ):

            if "is_org_change_complete" not in st.session_state:
                st.session_state.is_org_change_complete = True

            def set_org_in_query_params():
                st.query_params["org_id"] = st.session_state.selected_org["id"]

            def selected_org_changed():
                st.session_state.is_org_change_complete = False
                set_org_in_query_params()

            cols = st.sidebar.columns([6, 1])

            # make sure that if someone is coming from the admin panel to the home page,
            # the selected org is the one they came from
            if "org_id" in st.session_state and st.session_state.org_id is not None:
                st.session_state.selected_org = [
                    org
                    for org in st.session_state.user_orgs
                    if org["id"] == st.session_state.org_id
                ][0]

            selected_org = cols[0].selectbox(
                f'`{st.session_state["email"]}`',
                st.session_state.user_orgs,
                key="selected_org",
                format_func=lambda val: f"{val['name']} ({val['role']})",
                on_change=selected_org_changed,
            )

            if not selected_org["openai_api_key"]:
                st.sidebar.error(
                    """No OpenAI API key found. Please set an API key in the "Settings" section. Otherwise, AI will not work, neither for generating tasks nor for providing feedback."""
                )

            cols[1].container(height=10, border=False)
            cols[1].button(
                "",
                icon="➕",
                help="Create an organization",
                on_click=show_create_org_dialog,
                args=(st.session_state.user["id"],),
            )

            print(selected_org["id"])
            st.page_link(
                f"{os.environ.get('APP_URL')}/admin?org_id={selected_org['id']}",
                label="Admin Panel",
                icon="⚙️",
                disabled=not st.session_state.is_org_change_complete,
            )

            if not st.session_state.is_org_change_complete:
                st.session_state.is_org_change_complete = True
                st.rerun()

            return

        st.divider()

        st.markdown(
            """
            <div style="display: flex; align-items: flex-start; gap: 4px;">
                <h3 style="margin: 0;">Placement Prep</h3>
                <span style="background-color: #ffd700; padding: 1px 6px; border-radius: 4px; font-size: 0.6em; position: relative; top: 2px;">BETA</span>
            </div>
        """,
            unsafe_allow_html=True,
        )

        st.page_link(
            f"{os.environ.get('APP_URL')}/interview_practice",
            label="Practice for Interviews with AI",
            icon="🎙️",
        )

        st.page_link(
            f"{os.environ.get('APP_URL')}/cv_review",
            label="Polish your CV with AI",
            icon="📄",
        )


def menu(selected_cohort: Dict, role: str):
    show_toast()
    menu_header()

    if st.experimental_user.is_authenticated:
        authenticated_menu(selected_cohort, role)

    menu_footer(selected_cohort, role)
    # auth(label="Change your logged in email", key_suffix="menu",  sidebar=True)
