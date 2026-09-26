def get_inline_buttons(method):
    return [b for row in method.reply_markup.inline_keyboard for b in row]
