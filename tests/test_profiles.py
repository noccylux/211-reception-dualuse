from dualuse.profiles import PROFILES, fallback_question, language_of, line, welcome


def test_la_welcome_names_911_the_queue_position_and_other_languages():
    text = welcome("la-211", "en", ahead=0, reorders=True)
    assert "911" in text and "0" in text
    assert "español" in text and "中文" in text


def test_china_welcome_is_mandarin_with_local_emergency_numbers():
    text = welcome("cn-12345", "zh", ahead=2, reorders=True)
    assert all(number in text for number in ("110", "119", "120"))
    assert "2" in text and "排队" in text


def test_fifo_welcome_does_not_promise_reordering():
    assert welcome("la-211", "en", ahead=1, reorders=False) != welcome("la-211", "en", ahead=1, reorders=True)
    assert "change" not in welcome("la-211", "en", ahead=1, reorders=False).split("911")[0]


def test_emergency_line_follows_the_caller_language_and_keeps_the_profile_number():
    assert "911" in line("la-211", "emergency", "es") and "llame" in line("la-211", "emergency", "es").lower()
    assert "911" in line("la-211", "emergency", "zh") and "拨打" in line("la-211", "emergency", "zh")
    assert "120" in line("cn-12345", "emergency", "zh")


def test_unknown_language_falls_back_to_english():
    assert line("la-211", "reserved", "tl") == line("la-211", "reserved", "en")


def test_fallback_questions_exist_for_every_topic_in_profile_languages():
    for topic in ("situation", "location", "safety", "need", "detail"):
        assert fallback_question(topic, "zh").endswith("？")
        assert fallback_question(topic, "es").endswith("?")
    assert fallback_question("wait", "en") == ""


def test_language_codes_reduce_to_their_primary_subtag():
    assert language_of("zh-CN") == "zh" and language_of("es-MX") == "es" and language_of("") == "en"


def test_both_profiles_are_registered_with_their_languages():
    assert PROFILES["la-211"].languages == ("en", "es", "zh")
    assert PROFILES["cn-12345"].languages[0] == "zh"


def test_a_malformed_language_code_falls_back_to_english():
    assert language_of("[verify](http://x)") == "en" and language_of("zh-Hans-CN") == "zh"
