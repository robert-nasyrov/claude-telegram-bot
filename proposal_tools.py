"""
Proposal tool for Claude Tool Use.
Generates commercial proposals via natural language.
"""

import json
import base64
import logging

logger = logging.getLogger(__name__)


PROPOSAL_TOOLS = [
    {
        "name": "proposal_generate",
        "description": (
            "Generate a commercial proposal (KP) as a PDF document. "
            "Use when the user asks to create a proposal, KP, quote, or price estimate for a client. "
            "Also trigger when user forwards a client message asking about prices/services. "
            "Keywords: КП, коммерческое, proposal, quote, стоимость, прайс, клиент. "
            "IMPORTANT: After generating, tell the user to use /kp command with the client details "
            "to get the PDF file, since tool results cannot send files directly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "client_request": {
                    "type": "string",
                    "description": "Full client request including company name, contact, services needed.",
                },
            },
            "required": ["client_request"],
        },
    },
]


async def execute_tool(tool_name: str, tool_input: dict) -> str:
    try:
        if tool_name == "proposal_generate":
            import proposal
            client_request = tool_input["client_request"]
            pdf_bytes, data = await proposal.generate_proposal(client_request)

            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")
            client_name = data.get("client_company", "client")

            return json.dumps({
                "success": True,
                "client_company": client_name,
                "services_count": len(data.get("services", [])),
                "packages_count": len(data.get("packages", [])),
                "pdf_base64": pdf_b64,
                "_has_file": True,
                "_filename": f"KP_{client_name.replace(' ', '_')}.pdf",
            }, ensure_ascii=False, default=str)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        logger.error(f"Proposal tool error: {e}", exc_info=True)
        return json.dumps({"error": str(e)})
