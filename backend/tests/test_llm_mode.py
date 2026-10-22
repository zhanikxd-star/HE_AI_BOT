from app.adapters.llm import OpenAiCompatibleLlm, TestLlmAdapter, build_llm, llm_runtime_mode


def test_missing_openai_key_keeps_test_adapter():
    adapter, model = build_llm("openai", "org-model", None, "https://api.openai.com/v1")
    assert isinstance(adapter, TestLlmAdapter)
    assert model == "org-model"
    assert llm_runtime_mode("openai", None) == "test"
    assert llm_runtime_mode("openai", "") == "test"


def test_openai_key_selects_live_adapter_without_calling_it():
    adapter, model = build_llm("openai", "org-model", "configured", "https://api.openai.com/v1")
    assert isinstance(adapter, OpenAiCompatibleLlm)
    assert model == "org-model"
    assert llm_runtime_mode("test", "configured") == "test"
