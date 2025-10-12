# AGENTS Runbook

## Project Strcture and Aims
- Unified Python (FastAPI) backend and React (Vite + TypeScript) frontend for managing Hamilton robots, camera automation, scheduling, and monitoring workflows.

## Implementation Note
- Add implementation to docs/implementation-notes.md with newest note coming on top. 
- The note should aim for clarity and preciseness, while try to be as brief as possible. The note aims to keep tracks of the development process and guide future codex sessions. 
- For any requests proposed by the user: As always, review the relevant code, come up with ideas on how to fix them, then let the user know (before implementing). 

## Compile and Build
- cd `frontend` and runs "npm run build" to build frontend (on windows machine);
- embedded static frontend by running `python build_scripts/embed_resources.py`, followed by `python build_scripts/pyinstaller_build.py` to compile.
- The binary will be tested on Virtual Environment, so try to make sure everything works before compiling. 

## Development Workflow
- If running inside WSL: Make changes but dont build/compile. Notify the user when you are confident about the changes.
- If running on Windows: Make changes and build/compile. 