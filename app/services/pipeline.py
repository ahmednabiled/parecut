from typing import Protocol

from fastapi import Request


class PipelineRunner(Protocol):
    async def spawn(self, job_id: str) -> None: ...


class NullPipelineRunner:
    async def spawn(self, job_id: str) -> None:
        return None


def get_runner(request: Request) -> PipelineRunner:
    return request.app.state.runner
