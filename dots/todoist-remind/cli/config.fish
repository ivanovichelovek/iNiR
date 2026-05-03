# Shared config — sourced by all remind_*.fish scripts.
# Loads TODOIST_TOKEN and TODOIST_PROJECT_ID from ../.env

set -l _env (dirname (status --current-filename))/../.env
if test -f $_env
    for _line in (grep -v '^#' $_env | grep -v '^$')
        set -l _parts (string split -m 1 '=' $_line)
        if test (count $_parts) -eq 2
            set -gx $_parts[1] $_parts[2]
        end
    end
end

if test -z "$TODOIST_TOKEN"
    echo "Ошибка: TODOIST_TOKEN не задан."
    echo "Отредактируй ~/.local/share/todoist-remind/.env"
    exit 1
end

set -g _API "https://api.todoist.com/api/v1"
set -g _AUTH "Authorization: Bearer $TODOIST_TOKEN"
