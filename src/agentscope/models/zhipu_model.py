# -*- coding: utf-8 -*-
"""Model wrapper for ZhipuAI models"""
from abc import ABC
from typing import Union, Any, List, Sequence

from loguru import logger

from .model import ModelWrapperBase, ModelResponse
from ..message import MessageBase
from ..utils.tools import _convert_to_str

try:
    import zhipuai
except ImportError:
    zhipuai = None


class ZhipuAIWrapperBase(ModelWrapperBase, ABC):
    """The model wrapper for ZhipuAI API."""

    def __init__(
        self,
        config_name: str,
        model_name: str = None,
        api_key: str = None,
        generate_args: dict = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the zhipuai client.

        Args:
            config_name (`str`):
                The name of the model config.
            model_name (`str`, default `None`):
                The name of the model to use in ZhipuAI API.
            api_key (`str`, default `None`):
                The API key for ZhipuAI API. If not specified, it will
                be read from the environment variable.
            generate_args (`dict`, default `None`):
                The extra keyword arguments used in zhipuai api generation,
                e.g. `temperature`, `seed`.
        """

        if model_name is None:
            model_name = config_name
            logger.warning("model_name is not set, use config_name instead.")

        super().__init__(config_name=config_name)

        if zhipuai is None:
            raise ImportError(
                "Cannot find zhipuai package in current python environment.",
            )

        self.model_name = model_name
        self.generate_args = generate_args or {}

        self.client = zhipuai.ZhipuAI(
            api_key=api_key,
        )

        self._register_default_metrics()

    def format(
        self,
        *args: Union[MessageBase, Sequence[MessageBase]],
    ) -> Union[List[dict], str]:
        raise RuntimeError(
            f"Model Wrapper [{type(self).__name__}] doesn't "
            f"need to format the input. Please try to use the "
            f"model wrapper directly.",
        )


class ZhipuAIChatWrapper(ZhipuAIWrapperBase):
    """The model wrapper for ZhipuAI's chat API."""

    model_type: str = "zhipuai_chat"

    # TOTEST
    def _register_default_metrics(self) -> None:
        # Set monitor accordingly
        # TODO: set quota to the following metrics
        self.monitor.register(
            self._metric("call_counter"),
            metric_unit="times",
        )
        self.monitor.register(
            self._metric("prompt_tokens"),
            metric_unit="token",
        )
        self.monitor.register(
            self._metric("completion_tokens"),
            metric_unit="token",
        )
        self.monitor.register(
            self._metric("total_tokens"),
            metric_unit="token",
        )

    def __call__(
        self,
        messages: list,
        **kwargs: Any,
    ) -> ModelResponse:
        """Processes a list of messages to construct a payload for the ZhipuAI
        API call. It then makes a request to the ZhipuAI API and returns the
        response. This method also updates monitoring metrics based on the
        API response.

        Args:
            messages (`list`):
                A list of messages to process.
            **kwargs (`Any`):
                The keyword arguments to ZhipuAI chat completions API,
                e.g. `temperature`, `max_tokens`, `top_p`, etc. Please refer to
                https://open.bigmodel.cn/dev/api
                for more detailed arguments.

        Returns:
            `ModelResponse`:
                The response text in text field, and the raw response in
                raw field.

        Note:
            `parse_func`, `fault_handler` and `max_retries` are reserved for
            `_response_parse_decorator` to parse and check the response
            generated by model wrapper. Their usages are listed as follows:
                - `parse_func` is a callable function used to parse and check
                the response generated by the model, which takes the response
                as input.
                - `max_retries` is the maximum number of retries when the
                `parse_func` raise an exception.
                - `fault_handler` is a callable function which is called
                when the response generated by the model is invalid after
                `max_retries` retries.
        """

        # step1: prepare keyword arguments
        kwargs = {**self.generate_args, **kwargs}

        # step2: checking messages
        if not isinstance(messages, list):
            raise ValueError(
                "ZhipuAI `messages` field expected type `list`, "
                f"got `{type(messages)}` instead.",
            )
        if not all("role" in msg and "content" in msg for msg in messages):
            raise ValueError(
                "Each message in the 'messages' list must contain a 'role' "
                "and 'content' key for ZhipuAI API.",
            )

        # step3: forward to generate response
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            **kwargs,
        )

        # step4: record the api invocation if needed
        self._save_model_invocation(
            arguments={
                "model": self.model_name,
                "messages": messages,
                **kwargs,
            },
            response=response.model_dump(),
        )

        # step5: update monitor accordingly
        self.update_monitor(call_counter=1, **response.usage.model_dump())

        # step6: return response
        return ModelResponse(
            text=response.choices[0].message.content,
            raw=response.model_dump(),
        )

    def format(
        self,
        *args: Union[MessageBase, Sequence[MessageBase]],
    ) -> List[dict]:
        """Format the input string and dictionary into the format that
        ZhipuAI Chat API required.

        In this format function, the input messages are formatted into a
        single system messages with format "{name}: {content}" for each
        message. Note this strategy maybe not suitable for all scenarios,
        and developers are encouraged to implement their own prompt
        engineering strategies.

        Args:
            args (`Union[MessageBase, Sequence[MessageBase]]`):
                The input arguments to be formatted, where each argument
                should be a `Msg` object, or a list of `Msg` objects.
                In distribution, placeholder is also allowed.

        Returns:
            `List[dict]`:
                The formatted messages in the format that ZhipuAI Chat API
                required.
        """

        # Parse all information into a list of messages
        input_msgs = []
        for _ in args:
            if _ is None:
                continue
            if isinstance(_, MessageBase):
                input_msgs.append(_)
            elif isinstance(_, list) and all(
                isinstance(__, MessageBase) for __ in _
            ):
                input_msgs.extend(_)
            else:
                raise TypeError(
                    f"The input should be a Msg object or a list "
                    f"of Msg objects, got {type(_)}.",
                )

        messages = []

        # record dialog history as a list of strings
        dialogue = []
        for i, unit in enumerate(input_msgs):
            if i == 0 and unit.role == "system":
                # system prompt
                messages.append(
                    {
                        "role": unit.role,
                        "content": _convert_to_str(unit.content),
                    },
                )
            else:
                # Merge all messages into a dialogue history prompt
                dialogue.append(
                    f"{unit.name}: {_convert_to_str(unit.content)}",
                )

        dialogue_history = "\n".join(dialogue)

        user_content_template = "## Dialogue History\n{dialogue_history}"

        messages.append(
            {
                "role": "user",
                "content": user_content_template.format(
                    dialogue_history=dialogue_history,
                ),
            },
        )

        return messages


class ZhipuAIEmbeddingWrapper(ZhipuAIWrapperBase):
    """The model wrapper for ZhipuAI embedding API."""

    model_type: str = "zhipuai_embedding"

    def __call__(
        self,
        texts: str,
        **kwargs: Any,
    ) -> ModelResponse:
        """Embed the messages with ZhipuAI embedding API.

        Args:
            texts (`str`):
                The messages used to embed.
            **kwargs (`Any`):
                The keyword arguments to ZhipuAI embedding API,
                e.g. `encoding_format`, `user`. Please refer to
                https://open.bigmodel.cn/dev/api#text_embedding
                for more detailed arguments.

        Returns:
            `ModelResponse`:
                A list of embeddings in embedding field and the
                raw response in raw field.

        Note:
            `parse_func`, `fault_handler` and `max_retries` are reserved for
            `_response_parse_decorator` to parse and check the response
            generated by model wrapper. Their usages are listed as follows:
                - `parse_func` is a callable function used to parse and check
                the response generated by the model, which takes the response
                as input.
                - `max_retries` is the maximum number of retries when the
                `parse_func` raise an exception.
                - `fault_handler` is a callable function which is called
                when the response generated by the model is invalid after
                `max_retries` retries.
        """
        # step1: prepare keyword arguments
        kwargs = {**self.generate_args, **kwargs}

        # step2: forward to generate response
        response = self.client.embeddings.create(
            input=texts,
            model=self.model_name,
        )

        # step3: record the model api invocation if needed
        self._save_model_invocation(
            arguments={
                "model": self.model_name,
                "input": texts,
                **kwargs,
            },
            response=response.model_dump(),
        )

        # step4: update monitor accordingly
        self.update_monitor(call_counter=1, **response.usage.model_dump())

        # step5: return response
        response_json = response.model_dump()
        if len(response_json["data"]) == 0:
            return ModelResponse(
                embedding=response_json["data"]["embedding"][0],
                raw=response_json,
            )
        else:
            return ModelResponse(
                embedding=[_["embedding"] for _ in response_json["data"]],
                raw=response_json,
            )

    def _register_default_metrics(self) -> None:
        # Set monitor accordingly
        # TODO: set quota to the following metrics
        self.monitor.register(
            self._metric("call_counter"),
            metric_unit="times",
        )
        self.monitor.register(
            self._metric("prompt_tokens"),
            metric_unit="token",
        )
        self.monitor.register(
            self._metric("completion_tokens"),
            metric_unit="token",
        )
        self.monitor.register(
            self._metric("total_tokens"),
            metric_unit="token",
        )
