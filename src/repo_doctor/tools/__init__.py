from .fs import CloneRepoTool, ListFilesTool, ReadFileTool, SearchCodeTool

def build_tools(workspace: str):
    tools = [CloneRepoTool(workspace), ListFilesTool(), ReadFileTool(), SearchCodeTool()]
    return {t.name: t for t in tools}
