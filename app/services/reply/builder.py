from app.schemas.replies import AgentJobResult, AgentReply


def build_job_result(job_id: str, reply: AgentReply) -> AgentJobResult:
    return AgentJobResult(
        job_id=job_id,
        result=reply,
    )

