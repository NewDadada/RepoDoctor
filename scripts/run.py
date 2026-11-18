
from repo_doctor.config import settings
from repo_doctor.tools import build_tools
from repo_doctor.orchestrator import run_agent

if __name__ == "__main__":
    workspace = settings.workspace_dir
    tools = build_tools(workspace)
    state = run_agent(
        goal="Find one bug/TODO and propose a patch.",
        repo_url="https://github.com/psf/requests",
        workspace=workspace,
        tools=tools,
    )
    print(state.final_answer)
    print(f"\nsteps={len(state.steps)}")