#!/usr/bin/fish
source (dirname (status --current-filename))/fish_functions.fish

remind list
echo
read -P "ID для удаления (пусто = отмена): " reminder_id
if test -z "$reminder_id"
    echo "Отменено."
    exit 0
end

remind del "$reminder_id"
