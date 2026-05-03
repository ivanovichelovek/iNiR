#!/usr/bin/fish
source (dirname (status --current-filename))/config.fish

set _url "$_API/tasks"
if test -n "$TODOIST_PROJECT_ID"
    set _url "$_url?project_id=$TODOIST_PROJECT_ID"
end

set _resp (curl -sf -H $_AUTH "$_url" 2>/dev/null)
if test $status -ne 0
    echo "Ошибка: нет доступа к Todoist API (интернет/токен?)"
    exit 1
end

set _count (echo $_resp | jq 'length')
if test "$_count" = "0"
    echo "Нет активных напоминаний."
    exit 0
end

set _tasks (echo $_resp | jq -c 'sort_by(.due.datetime // .due.date // "z") | .[]')
set _i 1
for _task in $_tasks
    set _content (echo $_task | jq -r '.content')
    set _dt (echo $_task | jq -r '.due.datetime // .due.date // ""')
    if test -n "$_dt"
        set _local (date -d "$_dt" +"%d.%m.%Y %H:%M" 2>/dev/null; or echo $_dt)
    else
        set _local "без даты"
    end
    printf "  %2d. %-40s %s\n" $_i "$_content" "$_local"
    set _i (math $_i + 1)
end
