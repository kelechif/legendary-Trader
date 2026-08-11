"""Unit tests for Redis stream encode/decode and blocking consume (mocked Redis)."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import redis

from prop_algo.infra.stream import Stream, _decode, _encode


class TestStreamCodec(unittest.TestCase):
    def test_encode_decode_dataframe_and_tuple_keys(self):
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        payload = {("ACC1", "EURUSD"): df, "nested": {"ok": True}}
        roundtrip = _decode(_encode(payload))
        self.assertIn(("ACC1", "EURUSD"), roundtrip)
        pd.testing.assert_frame_equal(roundtrip[("ACC1", "EURUSD")], df)
        self.assertEqual(roundtrip["nested"]["ok"], True)


class TestStreamIO(unittest.TestCase):
    def test_consume_passes_block_ms_and_returns_none_when_empty(self):
        fake_redis = MagicMock()
        fake_redis.xreadgroup.return_value = []

        with patch("prop_algo.infra.stream.redis.Redis", return_value=fake_redis):
            with patch.dict(os.environ, {"STREAM_BLOCK_MS": "2500"}, clear=False):
                stream = Stream(host="localhost", port=6379)
                result = stream.consume("market", "g1", "c1")

        self.assertIsNone(result)
        fake_redis.xgroup_create.assert_called_once_with(
            "market", "g1", mkstream=True
        )
        fake_redis.xreadgroup.assert_called_once_with(
            "g1", "c1", {"market": ">"}, count=1, block=2500
        )

    def test_consume_explicit_block_overrides_env(self):
        fake_redis = MagicMock()
        fake_redis.xreadgroup.return_value = []

        with patch("prop_algo.infra.stream.redis.Redis", return_value=fake_redis):
            stream = Stream(host="localhost", port=6379)
            stream.consume("s", "g", "c", block=100)

        self.assertEqual(fake_redis.xreadgroup.call_args.kwargs["block"], 100)

    def test_consume_returns_decoded_payload_and_acks(self):
        df = pd.DataFrame({"close": [1.1, 1.2]})
        encoded = json.dumps(_encode({"symbol": "EURUSD", "df": df})).encode()
        fake_redis = MagicMock()
        fake_redis.xreadgroup.return_value = [
            (b"market", [(b"1-0", {b"data": encoded})])
        ]

        with patch("prop_algo.infra.stream.redis.Redis", return_value=fake_redis):
            stream = Stream(host="localhost", port=6379)
            data = stream.consume("market", "g1", "c1", block=500)

        self.assertEqual(data["symbol"], "EURUSD")
        pd.testing.assert_frame_equal(data["df"], df)
        fake_redis.xack.assert_called_once_with("market", "g1", b"1-0")

    def test_consume_ignores_existing_group_error(self):
        fake_redis = MagicMock()
        fake_redis.xgroup_create.side_effect = redis.ResponseError("BUSYGROUP")
        fake_redis.xreadgroup.return_value = []

        with patch("prop_algo.infra.stream.redis.Redis", return_value=fake_redis):
            stream = Stream(host="localhost", port=6379)
            self.assertIsNone(stream.consume("s", "g", "c", block=1))

    def test_publish_xadd_encoded_json(self):
        fake_redis = MagicMock()
        with patch("prop_algo.infra.stream.redis.Redis", return_value=fake_redis):
            stream = Stream(host="localhost", port=6379)
            stream.publish("signals", {"side": "BUY"})

        fake_redis.xadd.assert_called_once()
        args, _ = fake_redis.xadd.call_args
        self.assertEqual(args[0], "signals")
        body = json.loads(args[1]["data"])
        self.assertEqual(body["side"], "BUY")


if __name__ == "__main__":
    unittest.main()
