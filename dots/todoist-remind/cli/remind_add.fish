#!/usr/bin/fish
source (dirname (status --current-filename))/config.fish

set _today (date +"%d.%m.%Y")

read -P "Название: " _name
if test -z "$_name"
    echo "Отменено."
    exit 0
end

read -P "Дата [$_today]: " _date
if test -z "$_date"
    set _date $_today
end

if not string match -qr '^[0-9]{2}\.[0-9]{2}\.[0-9]{4}$' "$_date"
    echo "Ошибка: нужен формат ДД.ММ.ГГГГ"
    exit 1
end

read -P "Время (ЧЧ:ММ): " _time
if test -z "$_time"
    echo "Ошибка: время обязательно"
    exit 1
end

if not string match -qr '^[0-9]{2}:[0-9]{2}$' "$_time"
    echo "Ошибка: нужен формат ЧЧ:ММ"
    exit 1
end

# Convert DD.MM.YYYY + HH:MM → UTC ISO 8601 (Todoist expects UTC)
set _parts (string split '.' $_date)
set _iso_local "$_parts[3]-$_parts[2]-$_parts[1] $_time"
set _ts (date -d "$_iso_local" +%s 2>/dev/null)
if test $status -ne 0
    echo "Ошибка: недействительная дата"
    exit 1
end
if test $_ts -le (date +%s)
    echo "Ошибка: дата и время должны быть в будущем"
    exit 1
end
set _due_utc (date -d "$_iso_local" -u +"%Y-%m-%dT%H:%M:%SZ")

set _body (jq -n --arg c "$_name" --arg d "$_due_utc" '{content: $c, due_datetime: $d}')
if test -n "$TODOIST_PROJECT_ID"
    set _body (echo $_body | jq --arg p "$TODOIST_PROJECT_ID" '. + {project_id: $p}')
end

set _resp (curl -sf -X POST \
    -H $_AUTH \
    -H "Content-Type: application/json" \
    -d $_body \
    "$_API/tasks" 2>/dev/null)

if test $status -ne 0
    echo "Ошибка: не удалось добавить напоминание"
    exit 1
end

echo "Добавлено: $_name  —  $_date $_time"
