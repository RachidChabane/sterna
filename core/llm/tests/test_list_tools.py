"""
Tests for list_coding_agents and update_coding_agent tools.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase

from code_sessions.models import SubAgent
from llm.knowledge_base_tools import KNOWLEDGE_BASE_USER_CONTEXT
from llm.list_tools import list_coding_agents, update_coding_agent

User = get_user_model()


class ListCodingAgentsToolTest(TestCase):
    """Tests for the list_coding_agents tool."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )
        # Create test agents
        self.agent1 = SubAgent.objects.create(
            user=self.user,
            name="security-reviewer",
            description="Reviews code for security issues",
            model_tier="powerful",
            tools=["Read", "Glob", "Grep"],
            max_turns=15,
            permission_mode="plan",
            is_active=True,
        )
        self.agent2 = SubAgent.objects.create(
            user=self.user,
            name="test-writer",
            description="Writes unit tests",
            model_tier="balanced",
            tools=["Read", "Write", "Edit", "Bash"],
            max_turns=20,
            permission_mode="autoEdit",
            is_active=False,
        )
        # Agent belonging to another user
        self.other_agent = SubAgent.objects.create(
            user=self.user2,
            name="other-agent",
            description="Someone else's agent",
            model_tier="fast",
            is_active=True,
        )

    def _set_context(self, user):
        """Set the KNOWLEDGE_BASE_USER_CONTEXT for the given user."""
        KNOWLEDGE_BASE_USER_CONTEXT.set({'user': user})

    def test_list_agents_returns_correct_count(self):
        self._set_context(self.user)
        result = json.loads(list_coding_agents.invoke({}))
        self.assertEqual(result['total_agents'], 2)
        self.assertEqual(len(result['agents']), 2)

    def test_list_agents_returns_correct_fields(self):
        self._set_context(self.user)
        result = json.loads(list_coding_agents.invoke({}))
        agent = next(a for a in result['agents'] if a['name'] == 'security-reviewer')
        self.assertEqual(agent['description'], 'Reviews code for security issues')
        self.assertEqual(agent['model_tier'], 'powerful')
        self.assertEqual(agent['tools'], ['Read', 'Glob', 'Grep'])
        self.assertEqual(agent['max_turns'], 15)
        self.assertEqual(agent['permission_mode'], 'plan')
        self.assertTrue(agent['is_active'])

    def test_list_agents_empty(self):
        user3 = User.objects.create_user(
            email="empty@example.com", password="testpass123"
        )
        self._set_context(user3)
        result = json.loads(list_coding_agents.invoke({}))
        self.assertEqual(result['total_agents'], 0)
        self.assertEqual(result['agents'], [])

    def test_filter_by_is_active(self):
        self._set_context(self.user)
        result = json.loads(list_coding_agents.invoke({'is_active': True}))
        self.assertEqual(result['total_agents'], 1)
        self.assertEqual(result['agents'][0]['name'], 'security-reviewer')

    def test_filter_by_name_contains(self):
        self._set_context(self.user)
        result = json.loads(list_coding_agents.invoke({'name_contains': 'test'}))
        self.assertEqual(result['total_agents'], 1)
        self.assertEqual(result['agents'][0]['name'], 'test-writer')

    def test_user_isolation(self):
        """User A cannot see user B's agents."""
        self._set_context(self.user2)
        result = json.loads(list_coding_agents.invoke({}))
        self.assertEqual(result['total_agents'], 1)
        self.assertEqual(result['agents'][0]['name'], 'other-agent')

    def test_no_user_context(self):
        KNOWLEDGE_BASE_USER_CONTEXT.set(None)
        result = list_coding_agents.invoke({})
        self.assertIn("Error", result)


class UpdateCodingAgentToolTest(TestCase):
    """Tests for the update_coding_agent tool."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            email="other@example.com", password="testpass123"
        )
        self.agent = SubAgent.objects.create(
            user=self.user,
            name="my-agent",
            description="Original description",
            model_tier="balanced",
            tools=["Read", "Glob"],
            disallowed_tools=[],
            max_turns=10,
            permission_mode="default",
            is_active=True,
        )
        self.other_agent = SubAgent.objects.create(
            user=self.user2,
            name="other-agent",
            description="Other user's agent",
            model_tier="fast",
            is_active=True,
        )

    def _set_context(self, user):
        KNOWLEDGE_BASE_USER_CONTEXT.set({'user': user})

    def test_update_model_tier(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
            'model_tier': 'powerful',
        }))
        self.assertTrue(result['success'])
        self.assertEqual(result['agent']['model_tier'], 'powerful')
        # Verify in DB
        self.agent.refresh_from_db()
        self.assertEqual(self.agent.model_tier, 'powerful')

    def test_update_tools_list(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
            'tools': ['Read', 'Write', 'Edit', 'Bash'],
        }))
        self.assertTrue(result['success'])
        self.assertEqual(result['agent']['tools'], ['Read', 'Write', 'Edit', 'Bash'])

    def test_update_is_active_toggle(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
            'is_active': False,
        }))
        self.assertTrue(result['success'])
        self.assertFalse(result['agent']['is_active'])
        self.agent.refresh_from_db()
        self.assertFalse(self.agent.is_active)

    def test_update_by_id(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_id': str(self.agent.id),
            'description': 'Updated via ID',
        }))
        self.assertTrue(result['success'])
        self.assertEqual(result['agent']['description'], 'Updated via ID')

    def test_user_isolation_cannot_update_other_user_agent(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'other-agent',
            'model_tier': 'powerful',
        }))
        self.assertFalse(result['success'])
        self.assertIn("No coding agent found", result['error'])

    def test_invalid_model_tier(self):
        """Invalid model_tier is rejected by Pydantic schema validation."""
        self._set_context(self.user)
        with self.assertRaises(Exception):
            update_coding_agent.invoke({
                'agent_name': 'my-agent',
                'model_tier': 'turbo',
            })

    def test_invalid_tool_name(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
            'tools': ['Read', 'InvalidTool'],
        }))
        self.assertFalse(result['success'])
        self.assertIn("Invalid tool", result['error'])

    def test_agent_not_found(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'nonexistent',
            'model_tier': 'fast',
        }))
        self.assertFalse(result['success'])
        self.assertIn("No coding agent found", result['error'])

    def test_must_provide_id_or_name(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'model_tier': 'fast',
        }))
        self.assertFalse(result['success'])
        self.assertIn("must provide either", result['error'])

    def test_no_fields_to_update(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
        }))
        self.assertFalse(result['success'])
        self.assertIn("No update fields provided", result['error'])

    def test_tools_disallowed_overlap(self):
        self._set_context(self.user)
        result = json.loads(update_coding_agent.invoke({
            'agent_name': 'my-agent',
            'tools': ['Read', 'Write'],
            'disallowed_tools': ['Write'],
        }))
        self.assertFalse(result['success'])
        self.assertIn("cannot be both allowed and disallowed", result['error'])

    def test_invalid_permission_mode(self):
        """Invalid permission_mode is rejected by Pydantic schema validation."""
        self._set_context(self.user)
        with self.assertRaises(Exception):
            update_coding_agent.invoke({
                'agent_name': 'my-agent',
                'permission_mode': 'yolo',
            })
