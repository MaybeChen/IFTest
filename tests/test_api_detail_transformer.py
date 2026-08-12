from browser_ai_test.browser.api_detail_transformer import transform_api_details


def test_transforms_methods_and_recursively_expands_complex_types():
    data = {
        "tableData": [
            {
                "operationName": "accessToken",
                "request": [
                    {
                        "elements": [
                            {"name": "client_id", "type": "string", "length": None, "required": True},
                            {"name": "credentials", "type": "Credentials", "required": True},
                            {"name": "header", "type": "RequestHeader", "required": True},
                        ]
                    }
                ],
                "response": [
                    {
                        "elements": [
                            {"name": "access_token", "type": "string", "required": True},
                            {"name": "meta", "type": "Meta", "required": False},
                        ]
                    }
                ],
            }
        ],
        "complexTypes": [
            {
                "type": "Credentials",
                "elements": [
                    {"name": "secret", "type": "string", "length": 128, "minOccurs": 1}
                ],
            },
            {
                "key": "Meta",
                "elements": [
                    {"name": "expires_in", "type": "integer", "length": 10, "required": False}
                ],
            },
            {"type": "RequestHeader", "elements": [{"name": "version", "type": "string"}]},
        ],
    }

    assert transform_api_details(data) == [
        {
            "name": "accessToken",
            "request": [
                {"path": "$.client_id", "type": "string", "lenth": None, "required": True},
                {"path": "$.credentials.secret", "type": "string", "lenth": 128, "required": True},
            ],
            "response": [
                {"path": "$.access_token", "type": "string", "lenth": None, "required": True},
                {"path": "$.meta.expires_in", "type": "integer", "lenth": 10, "required": False},
            ],
        }
    ]


def test_supports_inline_elements_and_prevents_recursive_type_cycles():
    data = {
        "tableData": [
            {
                "operationName": "inline",
                "request": [{"elements": [{"name": "body", "type": "object", "elements": [
                    {"name": "value", "type": "string", "minOccurs": 0}
                ]}]}],
                "response": [{"elements": [{"name": "node", "type": "Node"}]}],
            }
        ],
        "complexTypes": [{"type": "Node", "elements": [{"name": "child", "type": "Node"}]}],
    }

    result = transform_api_details(data)

    assert result[0]["request"] == [
        {"path": "$.body.value", "type": "string", "lenth": None, "required": False}
    ]
    assert result[0]["response"] == []


def test_invalid_or_missing_collections_produce_empty_method_list():
    assert transform_api_details(None) == []
    assert transform_api_details({"tableData": None}) == []


def test_empty_message_elements_can_resolve_operation_key_complex_type():
    data = {
        "tableData": [{
            "operationName": "resolved",
            "request": [{"operationKey": "ReqMsg", "elements": []}],
            "response": [],
        }],
        "complexTypes": [{
            "key": "ReqMsg",
            "elements": [{"name": "id", "type": "string", "length": 64, "required": True}],
        }],
    }

    assert transform_api_details(data)[0]["request"] == [
        {"path": "$.id", "type": "string", "lenth": 64, "required": True}
    ]
