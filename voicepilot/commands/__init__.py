"""명령 사전 로딩과 매칭."""

from .loader import load_command_file
from .matcher import CommandMatcher, CommandSpec, Intent

__all__ = ["CommandMatcher", "CommandSpec", "Intent", "load_command_file"]
