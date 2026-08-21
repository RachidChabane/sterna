/**
 * Centralized Suggested Questions
 *
 * Single source of truth for all suggested questions used across the application.
 * Used by both SuggestedQuestions (grid view) and SuggestedQuestionsCarousel (carousel view).
 */

import {
  Code2,
  Brain,
  Sparkles,
  Globe,
  FileText,
  Database,
  Bug,
  BookOpen,
  BarChart3,
  FileJson,
  Wrench,
  Puzzle,
} from 'lucide-react'

export type QuestionCategory = 'code' | 'data' | 'creative'

export interface QuestionCategoryInfo {
  id: QuestionCategory
  label: string
  description: string
}

export interface SuggestedQuestion {
  icon: React.ComponentType<{ className?: string }>
  title: string
  description: string
  prompt: string
  category: QuestionCategory
}

export const QUESTION_CATEGORIES: QuestionCategoryInfo[] = [
  {
    id: 'code',
    label: 'Code',
    description: 'Programming and software development',
  },
  {
    id: 'data',
    label: 'Data',
    description: 'Analysis and information extraction',
  },
  {
    id: 'creative',
    label: 'Creative',
    description: 'Writing and problem solving',
  },
]

export const SUGGESTED_QUESTIONS: SuggestedQuestion[] = [
  {
    icon: Code2,
    title: 'Code Generation',
    description: 'Python palindrome function',
    prompt: 'Write a Python function that finds the longest palindromic substring in a given string.',
    category: 'code',
  },
  {
    icon: Bug,
    title: 'Code Debugging',
    description: 'Find and fix bugs',
    prompt: 'Find and explain all bugs in this Python code:\n\n```python\ndef calculate_average(numbers):\n    total = 0\n    for i in range(len(numbers)):\n        total += numbers[i]\n    return total / len(numbers)\n\nscores = [85, 90, 78, 92]\nprint(f"Average: {calculate_average([])}")\n```',
    category: 'code',
  },
  {
    icon: Wrench,
    title: 'Code Refactoring',
    description: 'Improve code quality',
    prompt: 'Refactor this code to make it more readable and efficient:\n\n```javascript\nfunction f(x) {\n  let r = [];\n  for (let i = 0; i < x.length; i++) {\n    if (x[i] % 2 == 0) {\n      r.push(x[i] * 2);\n    }\n  }\n  return r;\n}\n```',
    category: 'code',
  },
  {
    icon: Puzzle,
    title: 'Algorithm Design',
    description: 'Design efficient solution',
    prompt: 'Design an algorithm to find the two numbers in an array that sum to a specific target. Explain your approach, provide pseudocode, and analyze the time complexity.',
    category: 'code',
  },
  {
    icon: BarChart3,
    title: 'Data Analysis',
    description: 'Interpret dataset trends',
    prompt: 'Given a dataset of daily temperatures: [15, 18, 22, 25, 23, 19, 17, 20, 24, 26], identify any trends, calculate key statistics (mean, median, range), and make a prediction for the next day.',
    category: 'data',
  },
  {
    icon: Database,
    title: 'Data Extraction',
    description: 'Structured information retrieval',
    prompt: 'Extract the following information from this text and format it as JSON: "John Smith, age 34, works as a Senior Software Engineer at TechCorp in San Francisco. He can be reached at john.smith@email.com or 555-0123. He joined the company on March 15, 2020." Extract: name, age, job_title, company, location, email, phone, start_date.',
    category: 'data',
  },
  {
    icon: FileJson,
    title: 'Structured Output',
    description: 'Generate valid JSON',
    prompt: 'Create a JSON object representing a fictional company with the following fields: name, industry, founded_year, employees, headquarters (city and country), and 3 recent_products (each with name, price, and release_date).',
    category: 'data',
  },
  {
    icon: FileText,
    title: 'Summarization',
    description: 'Text summarization abilities',
    prompt: 'Summarize this article excerpt in 3 key bullet points: "Quantum computing represents a paradigm shift in computational power. Unlike classical computers that use bits (0 or 1), quantum computers use qubits that can exist in multiple states simultaneously through superposition. This allows them to process vast amounts of data in parallel. Major tech companies are investing billions in quantum research, with potential applications in cryptography, drug discovery, and climate modeling. However, quantum computers are extremely sensitive to environmental interference and require near-absolute-zero temperatures to operate."',
    category: 'data',
  },
  {
    icon: Sparkles,
    title: 'Creative Writing',
    description: 'Short story about time travel',
    prompt: 'Write a short story (150-200 words) about a time traveler who accidentally changes a small detail in the past.',
    category: 'creative',
  },
  {
    icon: Globe,
    title: 'Multilingual',
    description: 'Translation to 3 languages',
    prompt: 'Translate this sentence to French, Spanish, and Japanese: "The advancement of artificial intelligence is transforming how we interact with technology."',
    category: 'creative',
  },
  {
    icon: Brain,
    title: 'Reasoning',
    description: 'Multi-step math problem',
    prompt: 'If a car travels 120 km in 2 hours, then stops for 30 minutes, then travels another 90 km in 1.5 hours, what is its average speed for the entire journey?',
    category: 'creative',
  },
  {
    icon: BookOpen,
    title: 'Explain Concepts',
    description: 'Teaching and explanation styles',
    prompt: 'Explain how blockchain technology works in two ways: 1) To a 10-year-old child using simple analogies, and 2) To a computer science student with technical details.',
    category: 'creative',
  },
]
