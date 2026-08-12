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
