from .fs import CloneRepoTool, ReadFileTool, SearchCodeTool

def build_tools(workspace: str):
    tools = [CloneRepoTool(workspace), ReadFileTool(), SearchCodeTool()]
    return {t.name: t for t in tools}