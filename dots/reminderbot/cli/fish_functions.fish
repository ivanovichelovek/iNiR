# ReminderBot fish integration
# Add to ~/.config/fish/config.fish:
#   source /path/to/ReminderBot/cli/fish_functions.fish

set -gx REMINDERBOT_DIR (realpath (dirname (status --current-filename))/..)
# Если realpath недоступен, замени строку выше на абсолютный путь:
# set -gx REMINDERBOT_DIR /home/ivanc/GitHub/my-config/ReminderBot

function remind
    uv run --directory $REMINDERBOT_DIR python $REMINDERBOT_DIR/cli/remind.py $argv
end

# Quick shortcuts (optional):
#   remind-add "Buy milk" "04.05.2026 15:00"
#   remind-list
#   remind-del 5

function remind-add
    remind add $argv
end

function remind-list
    remind list $argv
end

function remind-del
    remind delete $argv
end
