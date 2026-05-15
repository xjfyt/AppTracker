from integrations.redaction import redact_cmdline


def test_redact_password_equals():
    cmd = ["mysql", "-u", "root", "--password=hunter2longenough", "db"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "hunter2longenough" not in " ".join(out)
    assert any(x.startswith("--password=") for x in out)


def test_redact_password_short_flag():
    cmd = ["mysql", "-p", "supersecret123"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "supersecret123" not in out


def test_redact_space_separated_token():
    cmd = ["curl", "--token", "sk-1234567890abcdef1234567890", "https://api"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "sk-1234567890abcdef1234567890" not in out


def test_keep_short_values():
    cmd = ["echo", "hi"]
    out, r = redact_cmdline(cmd)
    assert r is False
    assert out == cmd


def test_aws_key_value_pattern():
    cmd = ["aws", "s3", "ls", "AKIAIOSFODNN7EXAMPLE"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_github_pat_pattern():
    cmd = ["gh", "auth", "login", "--with-token", "ghp_abcdefghijklmnopqrstuvwxyz123456789012"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "ghp_abcdefghijklmnopqrstuvwxyz123456789012" not in out


def test_long_hex_pattern():
    long_hex = "a" * 64
    cmd = ["program", long_hex]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert long_hex not in out


def test_empty_cmdline():
    out, r = redact_cmdline([])
    assert out == []
    assert r is False


def test_case_insensitive_flag_match():
    cmd = ["app", "--PASSWORD=plainSecret123"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "plainSecret123" not in " ".join(out)


def test_anthropic_style_key():
    cmd = ["python", "script.py", "--api-key", "sk-ant-api01-aaaaaaaaaaaaaaaaaaaaaaaa"]
    out, r = redact_cmdline(cmd)
    assert r is True
    assert "sk-ant-api01-aaaaaaaaaaaaaaaaaaaaaaaa" not in out


def test_does_not_redact_normal_arg():
    cmd = ["ls", "-la", "/Users/me/Documents"]
    out, r = redact_cmdline(cmd)
    assert r is False
    assert out == cmd
