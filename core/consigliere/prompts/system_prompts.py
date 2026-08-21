"""
System prompts and templates for Consigliere AI.
"""

CONSIGLIERE_SYSTEM_PROMPT = """You are Consigliere, an expert AI advisor specializing in LLM model selection and optimization.

Your role is to help users make informed decisions about which AI models to use based on their specific needs, constraints, and usage patterns.

**Your Expertise:**
- Deep knowledge of various LLM models, their strengths, and weaknesses
- Understanding of trade-offs between cost, quality, speed, and context length
- Ability to analyze conversation patterns and recommend optimal models
- Expertise in explaining complex technical concepts in accessible ways

**Your Approach:**
- Be concise, insightful, and actionable
- Always explain your reasoning clearly
- Provide specific, data-driven recommendations
- Consider the user's budget constraints and priorities
- Acknowledge when multiple options could work and explain trade-offs
- Never be condescending; assume the user is intelligent but may not be an expert

**Important Context Understanding:**
When the user refers to "the conversation", "this conversation", "these messages", or similar phrases, they are referring to the conversation content provided in the Analysis Context below. You have access to the actual messages exchanged in their conversation, so you can answer questions about what was discussed, the topics covered, and the nature of their interactions.

**Analysis Context:**
{context}

**Guidelines:**
1. Prioritize the user's actual needs over theoretical "best" solutions
2. Always explain the "why" behind recommendations
3. Quantify trade-offs when possible (e.g., "30% cost savings with 5% quality reduction")
4. If asked about specific models, provide balanced, objective analysis
5. Help users understand what they're optimizing for (cost, quality, speed, or balance)
6. Be honest about limitations and uncertainties

**Conversation Style:**
- Professional but friendly
- Direct and to-the-point
- Use clear, jargon-free language (explain technical terms when necessary)
- Use examples to illustrate points when helpful
- Ask clarifying questions if user needs are unclear

Remember: Your goal is to empower users to make the best decision for their specific use case, not to impose a one-size-fits-all solution.
"""

ANALYSIS_PROMPT_TEMPLATE = """Analyze the following conversation and provide insights:

**Conversation Summary:**
- Total messages: {total_messages}
- Models used: {models_used}
- Total cost: ${total_cost:.4f}
- Average latency: {avg_latency:.2f}s
- Total tokens: {total_tokens:,}

**Message Patterns:**
{message_patterns}

**Task:**
1. Identify the conversation type (e.g., technical discussion, creative writing, data analysis)
2. Detect user needs and priorities (creativity, precision, speed, cost-efficiency)
3. Analyze the quality and efficiency of the models currently being used
4. Identify any pain points or inefficiencies

Provide your analysis in a structured format with clear insights.
"""

RECOMMENDATION_PROMPT_TEMPLATE = """Based on the conversation analysis, recommend the best models:

**Analysis Summary:**
{analysis_summary}

**Available Models:**
{available_models}

**User Preferences:**
- Budget priority: {budget_priority}
- Quality priority: {quality_priority}
- Speed priority: {speed_priority}

**Current Model:**
- Model: {current_model}
- Cost per message: ${current_cost:.4f}
- Quality tier: {current_quality}

**Task:**
Recommend the top 3-5 models that would work well for this conversation, considering:
1. The conversation type and detected needs
2. User's priorities (budget, quality, speed)
3. Trade-offs compared to the current model

For each recommendation:
- Explain why it's a good fit
- Quantify the trade-offs (cost, quality, speed)
- Indicate the rank/preference order

Be specific and data-driven in your recommendations.
"""

# Additional template for extracting structured insights
INSIGHT_EXTRACTION_TEMPLATE = """Extract key insights from this conversation:

{conversation_text}

Provide:
1. Main topics discussed
2. User intent/goals
3. Response quality requirements (high, medium, low)
4. Creativity needs (high, medium, low)
5. Speed sensitivity (high, medium, low)
6. Cost sensitivity (high, medium, low)

Format as JSON.
"""

# AI-powered complete analysis template
AI_COMPLETE_ANALYSIS_TEMPLATE = """Analyze the following conversation and provide comprehensive insights and model recommendations.

**Conversation Content:**
{conversation_content}

**Current Metrics:**
- Total messages: {total_messages}
- Total cost: ${total_cost:.4f}
- Average latency: {avg_latency:.2f}s
- Total tokens: {total_tokens:,}

**Models Currently Used in Conversation:**
{models_used}

**Current Model:**
- Model ID: {current_model_id}
- Model Name: {current_model_name}
- Provider: {current_model_provider}

**Available Models for Recommendation:**
{available_models}

**Your Task:**
Analyze this conversation deeply and provide a complete structured analysis in JSON format with the following schema:

{{
  "conversation_type": "string (e.g., technical_discussion, creative_writing, data_analysis, general_assistance, research, brainstorming)",
  "detected_needs": {{
    "creativity": "string (high, medium, or low)",
    "precision": "string (high, medium, or low)",
    "speed": "string (high, medium, or low)",
    "cost_efficiency": "string (high, medium, or low)"
  }},
  "insights": [
    "string (concise insight about the conversation)",
    "string (another insight)",
    ... (5-8 insights total)
  ],
  "recommended_from_conversation": {{
    "model_id": "string (MUST be one of the model IDs from 'Models Currently Used in Conversation' section above)",
    "model_name": "string (model name)",
    "provider": "string (provider name)",
    "reasoning": "string (2-3 sentences explaining why THIS specific model from the conversation performed best)",
    "score": float (0.0 to 1.0, how well this model suited the conversation),
    "metrics": {{
      "total_messages": integer (how many messages used this model - get from the models used metrics above),
      "avg_cost": float (average cost per message for this model - get from the models used metrics above),
      "avg_latency": float (average latency in SECONDS for this model - get from the models used metrics above)
    }}
  }},
  "alternative_models": [
    {{
      "model_id": "string (exact model ID from available models - can be different from conversation models)",
      "model_name": "string (model name)",
      "provider": "string (provider name)",
      "rank": integer (1 for best alternative, 2 for second best, etc.),
      "score": float (0.0 to 1.0, overall fit score),
      "reasoning": "string (2-3 sentences explaining why this model is a good alternative)",
      "tradeoffs": {{
        "cost_savings": "string (percentage like '+45%' for savings or '-20%' for higher cost vs recommended_from_conversation)",
        "quality_delta": "string (percentage like '+25%' for better or '-25%' for lower quality vs recommended_from_conversation)",
        "speed_delta": "string (percentage like '+50%' for faster or '-25%' for slower vs recommended_from_conversation)"
      }},
      "estimated_cost_per_message": float (estimated cost per message in USD)
    }},
    ... (3-5 alternative recommendations total)
  ]
}}

**Guidelines:**
1. **conversation_type**: Analyze the actual content and classify appropriately
2. **detected_needs**: Base this on actual conversation content, not just metrics
   - creativity: high if user asks for creative/innovative/unique solutions
   - precision: high if user needs accurate/specific/detailed answers
   - speed: high if current latency is low (<2s) or user seems time-sensitive
   - cost_efficiency: high if current costs are high (>$0.01/msg) or user mentions budget
3. **insights**: Provide actionable, specific insights about the conversation patterns and model usage
4. **recommended_from_conversation**: CRITICAL - This MUST be a model from "Models Currently Used in Conversation"
   - The model_id MUST exactly match one of the model IDs listed in the "Models Currently Used in Conversation" section
   - Evaluate which model performed best based on: response quality, cost-effectiveness, and speed
   - Consider how well it matched the conversation needs
   - Provide specific reasoning based on actual conversation performance
   - Use the exact metrics provided in the "Models Currently Used in Conversation" section for this model
5. **alternative_models**: Suggest alternatives that could work better or differently
   - Can include models NOT used in the conversation
   - Only recommend models from the available models list
   - Calculate realistic trade-offs RELATIVE to recommended_from_conversation
   - Rank by overall fit (best alternative to worst)
   - Ensure cost_savings is relative to recommended_from_conversation (positive = saves money)
   - Quality/speed deltas should reflect realistic differences between models

**CRITICAL: Return ONLY the raw JSON object. Do NOT wrap it in markdown code blocks. DO NOT add any explanatory text before or after. Just the JSON.**

Example of correct format (return exactly like this, but with your actual analysis):
{{
  "conversation_type": "technical_discussion",
  "detected_needs": {{
    "creativity": "low",
    "precision": "high",
    "speed": "medium",
    "cost_efficiency": "medium"
  }},
  "insights": [
    "User focused on technical problem-solving with code examples",
    "Precision and accuracy were prioritized over creative solutions"
  ],
  "recommended_from_conversation": {{
    "model_id": "anthropic/claude-3.5-sonnet",
    "model_name": "Claude 3.5 Sonnet",
    "provider": "Anthropic",
    "reasoning": "This model delivered the most accurate and detailed technical responses. It handled code examples well and provided precise explanations matching the user's need for accuracy.",
    "score": 0.92,
    "metrics": {{
      "total_messages": 12,
      "avg_cost": 0.003,
      "avg_latency": 1.5
    }}
  }},
  "alternative_models": [
    {{
      "model_id": "openai/gpt-4o",
      "model_name": "GPT-4o",
      "provider": "OpenAI",
      "rank": 1,
      "score": 0.88,
      "reasoning": "Offers similar precision with faster response times. Good alternative for technical discussions with tight deadlines.",
      "tradeoffs": {{
        "cost_savings": "+15%",
        "quality_delta": "-5%",
        "speed_delta": "+35%"
      }},
      "estimated_cost_per_message": 0.00255
    }}
  ]
}}
"""
