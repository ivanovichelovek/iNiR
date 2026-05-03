#!/usr/bin/fish
source (dirname (status --current-filename))/fish_functions.fish

set today (date +"%d.%m.%Y")

read -P "Название: " reminder_name
if test -z "$reminder_name"
    echo "Отменено."
    exit 0
end

read -P "Дата [$today]: " input_date
if test -z "$input_date"
    set input_date $today
end

if not string match -qr '^[0-9]{2}\.[0-9]{2}\.[0-9]{4}$' "$input_date"
    echo "Ошибка: нужен формат ДД.ММ.ГГГГ"
    exit 1
end

read -P "Время (ЧЧ:ММ): " input_time
if test -z "$input_time"
    echo "Ошибка: время обязательно"
    exit 1
end

if not string match -qr '^[0-9]{2}:[0-9]{2}$' "$input_time"
    echo "Ошибка: нужен формат ЧЧ:ММ"
    exit 1
end

set h (string split ":" "$input_time")[1]
set m (string split ":" "$input_time")[2]
if test $h -gt 23 -o $m -gt 59
    echo "Ошибка: часы 00–23, минуты 00–59"
    exit 1
end

# Convert DD.MM.YYYY → YYYY-MM-DD for date(1)
set parts (string split "." "$input_date")
set iso "$parts[3]-$parts[2]-$parts[1]"
set remind_ts (date -d "$iso $input_time" +%s 2>/dev/null)
if test $status -ne 0
    echo "Ошибка: недействительная дата"
    exit 1
end

if test $remind_ts -le (date +%s)
    echo "Ошибка: дата и время должны быть в будущем"
    exit 1
end

remind add "$reminder_name" "$input_date $input_time"
