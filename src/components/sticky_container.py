
from typing import Literal
import streamlit as st
from streamlit_theme import st_theme

MARGINS = {
    "top": "2rem",
    "bottom": "0",
}

STICKY_CONTAINER_HTML = """
<style>
div[data-testid="stVerticalBlock"] div:has(div.fixed-header-{i}) {{
    position: sticky;
    {position}: {margin};
    background-color: {background_color};
    color: {text_color};
    z-index: 999;
}}
</style>
<div class='fixed-header-{i}'/>
""".strip()

# Not to apply the same style to multiple containers
count = 0


DEFAULT_BACKGROUND_COLOR = '#000000'
DEFAULT_TEXT_COLOR = '#FFFFFF'

def sticky_container(
    *,
    container_cls = st.container,
    height: int  = None,
    border: bool  = None,
    mode: Literal["top", "bottom"] = "top",
    margin: str  = None,
):
    theme = st_theme()
    # st.write(theme)

    if margin is None:
        margin = MARGINS[mode]

    global count

    kwargs = {
        'background_color': DEFAULT_BACKGROUND_COLOR,
        'text_color': DEFAULT_TEXT_COLOR,
    }
    if theme is not None:
        kwargs['background_color'] = theme['backgroundColor']
        kwargs['text_color'] = theme['textColor']
    html_code = STICKY_CONTAINER_HTML.format(position=mode, margin=margin, i=count, **kwargs)
    count += 1

    container = container_cls(height=height, border=border)
    container.markdown(html_code, unsafe_allow_html=True)
    return container