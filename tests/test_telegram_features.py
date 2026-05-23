from mafia_bot.bot.telegram_features import dashboard_keyboard


def test_dashboard_keyboard_uses_copy_text_and_url_for_groups() -> None:
    keyboard = dashboard_keyboard("http://localhost:8000/chats/-100", use_web_app=False)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert buttons[0].url == "http://localhost:8000/chats/-100"
    assert buttons[1].copy_text is not None
    assert buttons[1].copy_text.text == "http://localhost:8000/chats/-100"
    assert all(button.web_app is None for button in buttons)


def test_dashboard_keyboard_can_use_mini_app_button_in_private_chat() -> None:
    keyboard = dashboard_keyboard("https://example.com/chats/-100", use_web_app=True)
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert buttons[0].web_app is not None
    assert buttons[0].style == "primary"
