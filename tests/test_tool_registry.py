# 验证工具注册、执行、超时、日志和结果边界。

import asyncio

import pytest
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import CurrentUser
from app.tools.base import ToolContext, ToolSpec
from app.tools.executor import execute_tool
from app.tools.registry import ToolRegistry


class EchoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)


async def echo_handler(
    args: EchoArgs,
    context: ToolContext,
) -> dict:
    return {
        "message": args.message,
        "user_id": context.current_user.id,
    }


async def broken_handler(
    args: EchoArgs,
    context: ToolContext,
) -> dict:
    raise RuntimeError("不应暴露给模型的内部错误")


def make_context() -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=7,
            username="test_user",
            role="admin",
        )
    )


def make_tool() -> ToolSpec:
    return ToolSpec(
        name="echo_message",
        description="返回一段测试消息。",
        args_model=EchoArgs,
        handler=echo_handler,
    )


def test_registry_returns_registered_tool():
    registry = ToolRegistry()
    tool = make_tool()

    registry.register(tool)

    assert registry.get("echo_message") is tool


def test_registry_rejects_duplicate_tool_name():
    registry = ToolRegistry()
    registry.register(make_tool())

    with pytest.raises(ValueError, match="工具已注册"):
        registry.register(make_tool())


def test_registry_returns_openai_definitions():
    registry = ToolRegistry()
    registry.register(make_tool())

    definitions = registry.openai_definitions()

    assert len(definitions) == 1
    assert definitions[0]["function"]["name"] == "echo_message"


def test_openai_definition_contains_parameter_schema():
    definition = make_tool().openai_definition()
    parameters = definition["function"]["parameters"]

    assert parameters["type"] == "object"
    assert "message" in parameters["properties"]
    assert "message" in parameters["required"]


def test_openai_definition_rejects_extra_fields():
    definition = make_tool().openai_definition()
    parameters = definition["function"]["parameters"]

    assert parameters["additionalProperties"] is False


@pytest.mark.parametrize(
    ("name", "description"),
    [
        ("", "有效描述"),
        ("   ", "有效描述"),
        ("valid_name", ""),
        ("valid_name", "   "),
    ],
)
def test_tool_spec_rejects_empty_name_or_description(
    name: str,
    description: str,
):
    with pytest.raises(ValueError):
        ToolSpec(
            name=name,
            description=description,
            args_model=EchoArgs,
            handler=echo_handler,
        )


def test_execute_tool_returns_result_and_injects_user_context():
    registry = ToolRegistry()
    registry.register(make_tool())

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="echo_message",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": True,
        "result": {
            "message": "hello",
            "user_id": 7,
        },
    }


def test_execute_tool_rejects_unknown_tool():
    registry = ToolRegistry()

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="delete_everything",
            arguments={},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具未注册",
    }


def test_execute_tool_rejects_non_object_arguments():
    registry = ToolRegistry()
    registry.register(make_tool())

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="echo_message",
            arguments=["hello"],
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数必须是 JSON 对象",
    }


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"message": 123},
    ],
)
def test_execute_tool_rejects_invalid_arguments(arguments: dict):
    registry = ToolRegistry()
    registry.register(make_tool())

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="echo_message",
            arguments=arguments,
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }


def test_execute_tool_hides_internal_handler_error():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="broken_tool",
            description="用于验证异常边界。",
            args_model=EchoArgs,
            handler=broken_handler,
        )
    )

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="broken_tool",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具执行失败",
    }
    assert "内部错误" not in str(result)


async def model_result_handler(
    args: EchoArgs,
    context: ToolContext,
) -> dict:
    return EchoArgs(message=args.message)


async def non_serializable_handler(
    args: EchoArgs,
    context: ToolContext,
) -> dict:
    return {"message": object()}


@pytest.mark.parametrize(
    "invalid_name",
    [
        " ",
        "get candidate profile",
        "工具-名称",
        ".",
        "a" * 65,
    ],
)
def test_tool_spec_rejects_invalid_tool_name_format(
    invalid_name: str,
):
    with pytest.raises(ValueError, match="工具名必须为"):
        ToolSpec(
            name=invalid_name,
            description="有效描述",
            args_model=EchoArgs,
            handler=echo_handler,
        )


def test_execute_tool_rejects_non_dict_handler_result():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="model_result",
            description="用于验证非字典返回值。",
            args_model=EchoArgs,
            handler=model_result_handler,
        )
    )

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="model_result",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具返回结果必须是 JSON 对象",
    }


def test_execute_tool_rejects_non_serializable_handler_result():
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="non_serializable",
            description="用于验证不可序列化返回值。",
            args_model=EchoArgs,
            handler=non_serializable_handler,
        )
    )

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="non_serializable",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具返回结果无法序列化",
    }


async def slow_handler(
    args: EchoArgs,
    context: ToolContext,
) -> dict:
    await asyncio.sleep(0.05)
    return {"message": args.message}


def test_execute_tool_logs_success_without_argument_value(caplog):
    import logging

    caplog.set_level(logging.INFO)
    registry = ToolRegistry()
    registry.register(make_tool())

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="echo_message",
            arguments={"message": "secret-message-value"},
            context=make_context(),
        )
    )

    assert result["ok"] is True
    assert "tool=echo_message" in caplog.text
    assert "user_id=7" in caplog.text
    assert "status=success" in caplog.text
    assert "duration_ms=" in caplog.text
    assert "secret-message-value" not in caplog.text


def test_execute_tool_logs_unknown_tool_as_warning(caplog):
    import logging

    caplog.set_level(logging.INFO)

    result = asyncio.run(
        execute_tool(
            registry=ToolRegistry(),
            tool_name="delete_everything",
            arguments={},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具未注册",
    }
    assert any(
        record.levelno == logging.WARNING
        and "status=unknown_tool" in record.getMessage()
        for record in caplog.records
    )


def test_execute_tool_validation_log_does_not_expose_values(caplog):
    import logging

    caplog.set_level(logging.INFO)
    registry = ToolRegistry()
    registry.register(make_tool())

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="echo_message",
            arguments={
                "message": 123,
                "secret": "sensitive-value",
            },
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具参数校验失败",
    }
    assert "status=validation_error" in caplog.text
    assert "sensitive-value" not in caplog.text
    assert "123" not in caplog.text


def test_execute_tool_timeout_returns_safe_error(caplog, monkeypatch):
    import logging

    import app.tools.executor as executor_module

    caplog.set_level(logging.INFO)
    monkeypatch.setattr(executor_module, "TOOL_TIMEOUT_SECONDS", 0.01)
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="slow_tool",
            description="用于验证超时。",
            args_model=EchoArgs,
            handler=slow_handler,
        )
    )

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="slow_tool",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具执行超时",
    }
    assert "status=timeout" in caplog.text
    assert "tool=slow_tool" in caplog.text
    assert "duration_ms=" in caplog.text


def test_execute_tool_internal_error_logs_and_returns_safe_result(caplog):
    import logging

    caplog.set_level(logging.INFO)
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="broken_tool",
            description="用于验证异常边界。",
            args_model=EchoArgs,
            handler=broken_handler,
        )
    )

    result = asyncio.run(
        execute_tool(
            registry=registry,
            tool_name="broken_tool",
            arguments={"message": "hello"},
            context=make_context(),
        )
    )

    assert result == {
        "ok": False,
        "error": "工具执行失败",
    }
    assert any(
        record.levelno == logging.ERROR
        and "status=error" in record.getMessage()
        for record in caplog.records
    )
    assert "内部错误" not in str(result)


def make_audit_context() -> ToolContext:
    return ToolContext(
        current_user=CurrentUser(
            id=7,
            username="test_user",
            role="admin",
        ),
        collect_tool_audit=True,
    )


def run_audited_tool(
    registry: ToolRegistry,
    *,
    tool_name: str,
    arguments: object,
    context: ToolContext,
) -> dict:
    return asyncio.run(
        execute_tool(
            registry=registry,
            tool_name=tool_name,
            arguments=arguments,
            context=context,
            step_no=3,
            tool_call_id=f"call-{tool_name}",
        )
    )


def test_execute_tool_records_success_audit_without_values():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(make_tool())

    result = run_audited_tool(
        registry,
        tool_name="echo_message",
        arguments={"message": "secret-value"},
        context=context,
    )

    assert result["ok"] is True
    assert len(context.tool_audit_events) == 1
    event = context.tool_audit_events[0]
    assert event.status == "success"
    assert event.step_no == 3
    assert event.tool_call_id == "call-echo_message"
    assert event.argument_keys == ["message"]
    assert event.duration_ms is not None
    assert "secret-value" not in event.model_dump_json()


def test_execute_tool_records_unknown_tool_audit():
    context = make_audit_context()

    run_audited_tool(
        ToolRegistry(),
        tool_name="missing_tool",
        arguments={},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "unknown_tool"
    assert event.error_code == "unknown_tool"


def test_execute_tool_records_non_object_argument_audit():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(make_tool())

    run_audited_tool(
        registry,
        tool_name="echo_message",
        arguments=["hello"],
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "validation_error"
    assert event.error_code == "invalid_arguments"
    assert event.argument_keys == []


def test_execute_tool_records_validation_audit():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(make_tool())

    run_audited_tool(
        registry,
        tool_name="echo_message",
        arguments={"message": 123},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "validation_error"
    assert event.error_code == "validation_error"
    assert event.argument_keys == ["message"]
    assert "123" not in event.model_dump_json()


def test_execute_tool_records_timeout_audit(monkeypatch):
    import app.tools.executor as executor_module

    monkeypatch.setattr(executor_module, "TOOL_TIMEOUT_SECONDS", 0.01)
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="slow_tool",
            description="用于验证超时审计。",
            args_model=EchoArgs,
            handler=slow_handler,
        )
    )

    run_audited_tool(
        registry,
        tool_name="slow_tool",
        arguments={"message": "hello"},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "timeout"
    assert event.error_code == "timeout"


def test_execute_tool_records_internal_error_audit():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="broken_tool",
            description="用于验证异常审计。",
            args_model=EchoArgs,
            handler=broken_handler,
        )
    )

    run_audited_tool(
        registry,
        tool_name="broken_tool",
        arguments={"message": "hello"},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "error"
    assert event.error_code == "handler_error"
    assert "内部错误" not in event.model_dump_json()


def test_execute_tool_records_invalid_result_audit():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="model_result",
            description="用于验证返回值类型审计。",
            args_model=EchoArgs,
            handler=model_result_handler,
        )
    )

    run_audited_tool(
        registry,
        tool_name="model_result",
        arguments={"message": "hello"},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "error"
    assert event.error_code == "invalid_result"


def test_execute_tool_records_non_serializable_audit():
    context = make_audit_context()
    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="non_serializable",
            description="用于验证序列化审计。",
            args_model=EchoArgs,
            handler=non_serializable_handler,
        )
    )

    run_audited_tool(
        registry,
        tool_name="non_serializable",
        arguments={"message": "hello"},
        context=context,
    )

    event = context.tool_audit_events[0]
    assert event.status == "error"
    assert event.error_code == "non_serializable_result"


def test_execute_tool_does_not_collect_audit_when_disabled():
    context = make_context()
    registry = ToolRegistry()
    registry.register(make_tool())

    run_audited_tool(
        registry,
        tool_name="echo_message",
        arguments={"message": "hello"},
        context=context,
    )

    assert context.tool_audit_events == []
