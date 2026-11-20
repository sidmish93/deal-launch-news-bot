import unittest

from newsbot.deal_bot import _apply_group_event, _group_event, _migrated_chat_id, _replace_chat


def _join(chat_id: int, status: str = "administrator") -> dict:
    return {
        "my_chat_member": {
            "chat": {"id": chat_id, "type": "supergroup"},
            "new_chat_member": {"status": status},
        }
    }


class GroupEventTests(unittest.TestCase):
    def test_admin_join_is_kept_beside_the_private_chat(self):
        state = {"chats": [1927167176], "welcomed": [1927167176]}
        event = _group_event(_join(-100123))
        self.assertEqual(_apply_group_event(state, event), "added")
        self.assertEqual(state["chats"], [1927167176, -100123])
        self.assertIn(-100123, state["welcomed"])
        self.assertEqual(_apply_group_event(state, event), "kept")
        self.assertEqual(state["chats"], [1927167176, -100123])

    def test_private_messages_do_not_change_the_chat_list(self):
        update = {"message": {"chat": {"id": 1927167176, "type": "private"}, "text": "hello"}}
        self.assertIsNone(_group_event(update))

    def test_a_group_message_counts_as_a_join(self):
        update = {"message": {"chat": {"id": -10055, "type": "group"}, "text": "created"}}
        self.assertEqual(_group_event(update), ("join", -10055))

    def test_leaving_removes_only_that_group(self):
        state = {"chats": [1927167176, -100123], "welcomed": [1927167176, -100123]}
        event = _group_event(_join(-100123, "left"))
        self.assertEqual(_apply_group_event(state, event), "removed")
        self.assertEqual(state["chats"], [1927167176])
        self.assertEqual(state["welcomed"], [1927167176])

    def test_an_upgraded_group_keeps_one_id(self):
        exc = RuntimeError(
            'sendMessage 400 {"parameters":{"migrate_to_chat_id":-1004356514851}}'
        )
        self.assertEqual(_migrated_chat_id(exc), -1004356514851)
        state = {"chats": [1927167176, -5577503059, -1004356514851], "welcomed": [1927167176, -5577503059]}
        _replace_chat(state, -5577503059, -1004356514851)
        self.assertEqual(state["chats"], [1927167176, -1004356514851])
        self.assertEqual(state["welcomed"], [1927167176, -1004356514851])
