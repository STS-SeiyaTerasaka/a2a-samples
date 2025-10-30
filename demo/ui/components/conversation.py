import dataclasses
import uuid

import mesop as me

from a2a.types import Message, Part, Role
from state.host_agent_service import SendMessage
from state.state import AppState, StateMessage

from .chat_bubble import chat_bubble
from .form_render import form_sent, is_form, render_form


@me.stateclass
class ConversationState:
    """Local Page State for the conversation component."""

    # This is used to reset the input field after a message is sent.
    textarea_key: int = 0


async def on_submit(e: me.InputEnterEvent):
    """Form submission handler"""
    state = me.state(AppState)
    convo_state = me.state(ConversationState)

    # Immediately clear the input field by updating the key
    convo_state.textarea_key += 1
    state.is_processing_message = True
    yield

    try:
        message = Message(
            message_id=str(uuid.uuid4()),
            context_id=state.current_conversation_id,
            role=Role.user,
            parts=[Part(text=e.value)],
        )
        # Add user's message to the local state immediately for responsiveness
        state.messages.append(
            StateMessage(
                message_id=message.message_id,
                role=Role.user.name,
                content=[(e.value, 'text/plain')],
            )
        )
        yield

        # Send the message to the backend
        await SendMessage(message)
    finally:
        # The polling mechanism will set this to False once an agent response is detected.
        pass


@me.component
def conversation():
    """Conversation component"""
    app_state = me.state(AppState)
    convo_state = me.state(ConversationState)

    if 'conversation_id' in me.query_params:
        app_state.current_conversation_id = me.query_params['conversation_id']

    with me.box(
        style=me.Style(
            display='flex',
            flex_direction='column',
            height='100%',
        )
    ):
        # Chat history
        with me.box(
            style=me.Style(
                flex_grow=1,
                overflow_y='auto',
                padding=me.Padding(right=12),
            )
        ):
            for message in app_state.messages:
                if is_form(message):
                    render_form(message, app_state)
                elif form_sent(message, app_state):
                    chat_bubble(
                        StateMessage(
                            message_id=message.message_id,
                            role=message.role,
                            content=[('Form submitted', 'text/plain')],
                        ),
                        message.message_id,
                    )
                else:
                    chat_bubble(message, message.message_id)

        # Spacer to push input to the bottom
        me.box(style=me.Style(flex_grow=1))

        # Message input area
        with me.box(
            style=me.Style(
                padding=me.Padding(top=16),
                border=me.Border(
                    top=me.BorderSide(
                        width=1, style='solid', color=me.theme_var('outline')
                    )
                ),
            )
        ):
            if app_state.is_processing_message:
                me.progress_spinner()

            me.input(
                key=str(convo_state.textarea_key),
                label='How can I help you?',
                on_enter=on_submit,
                style=me.Style(width='100%'),
                disabled=app_state.is_processing_message,
            )
