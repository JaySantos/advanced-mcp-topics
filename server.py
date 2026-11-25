from mcp.server.fastmcp import Context, FastMCP
from mcp.types import SamplingMessage, TextContent

mcp = FastMCP(name="Demo Server")


@mcp.tool(name="summarize", description="Returns the summary of a given text")
async def summarize(text_to_summarize: str, ctx: Context):
    prompt = f"""
        Please summarize the following text:
        {text_to_summarize}
    """

    await ctx.info("Initializing...")
    await ctx.report_progress(20, 100)
    result = await ctx.session.create_message(
        messages=[
            SamplingMessage(role="user", content=TextContent(type="text", text=prompt))
        ],
        max_tokens=4000,
        system_prompt="You are a helpful research assistant.",
    )
    await ctx.info("Summary received...")
    await ctx.report_progress(70, 100)
    if result.content.type == "text":
        return result.content.text
    else:
        raise ValueError("Sampling failed")


if __name__ == "__main__":
    mcp.run(transport="stdio")
