from browser_ai_test.config import AppConfig


def test_stream_timeout_defaults_to_two_hours() -> None:
    config = AppConfig.model_validate(
        {
            "browser": {},
            "system": {"url": "https://test"},
            "stream": {
                "url_keywords": ["/chat"],
                "done_markers": ["[DONE]"],
            },
        }
    )

    assert config.stream.timeout_seconds == 7_200
    assert config.runner.pass_condition == "network_complete"
    assert not config.stream.aborted_sse_is_complete
    assert not config.stream.sse_loading_finished_is_complete
    assert config.stream.done_event_names == []
    assert config.logging.file.as_posix() == "reports/browser-ai-test.log"
    assert config.api_detail.request_event == "getApiDetail"
    assert config.api_detail.response_event == "getApiDetail"
