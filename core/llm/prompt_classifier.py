"""
Deterministic prompt type classifier (keyword + signal based).

Heuristics only — no ML. Designed to be predictable and explainable.

Inputs:
- typed_text: the raw user-entered text (string)
- files: list of file descriptors (dict) with optional keys:
    { 'filename': str, 'mime': str | None, 'size': int | None }

Outputs:
- dict with keys:
    {
      'task_primary': str,
      'task_candidates': list[(task, score)],
      'signals': { ... },
      'reason': str,
    }

Also provides default per-task coefficients for completion estimation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from .estimation_config import CHARS_PER_TOKEN


# Canonical task names
TASKS = [
    'summarization',
    'translation',
    'rewriting',
    'question_answering',
    'extraction',
    'classification',
    'sentiment_analysis',
    'code_generation',
    'code_explanation',
    'data_analysis',
    'explanation',
    'outline',
    'brainstorm',
]

# Tasks whose presence in typed keywords can override summarization even when files are attached
# Order implies priority when multiple override tasks are detected
OVERRIDE_PRIORITY = [
    'translation',
    'code_generation',
    'code_explanation',
    'question_answering',
    'extraction',
    'data_analysis',
    'classification',
    'sentiment_analysis',
    'rewriting',
    'explanation',
]


# Keyword lexicon (EN + FR) — lowercased, simple contain checks
KEYWORDS: Dict[str, List[str]] = {
    'summarization': [
        'summarize', 'tl;dr', 'summary', 'synthesize', 'condense',
        'résume', 'résumer', 'résumé', 'synthétise', 'synthétiser', 'synthèse', 'condense',
    ],
    'translation': [
        'translate', 'translation', 'traduis', 'traduire', 'traduction', 'en anglais', 'en français', 'in english', 'into french'
    ],
    'rewriting': [
        'rewrite', 'rephrase', 'paraphrase', 'improve writing', 'refactor text',
        'réécris', 'réécrire', 'reformule', 'reformuler', 'améliore le texte'
    ],
    'question_answering': [
        'who', 'what', 'when', 'where', 'why', 'how', 'which', '?',
        'qui', 'quoi', 'quand', 'où', 'pourquoi', 'comment', 'lequel'
    ],
    'extraction': [
        'extract', 'pull fields', 'parse', 'structured data', 'regex',
        'extrais', 'extraire', 'extraction', 'champs', 'structuré'
    ],
    'classification': [
        'classify', 'categorize', 'label', 'category',
        'classe', 'classifier', 'catégorise', 'catégorie'
    ],
    'sentiment_analysis': [
        'sentiment', 'opinion', 'positive', 'negative', 'neutral',
        'avis', 'opinion', 'positif', 'négatif', 'neutre'
    ],
    'code_generation': [
        'write code', 'implement', 'generate code', 'function', 'algorithm', 'api', 'fix bug', 'unit test',
        'écris du code', 'implémente', 'implémenter', 'génère du code', 'fonction', 'algorithme', 'corrige', 'tests unitaires'
    ],
    'code_explanation': [
        'explain code', 'explain this function', 'what does this code do',
        'explique ce code', 'explique la fonction', 'que fait ce code'
    ],
    'data_analysis': [
        'analyze data', 'plot', 'chart', 'aggregate', 'pivot', 'statistic', 'csv', 'jsonl', 'json',
        'analyse des données', 'graphique', 'agréger', 'tableau croisé', 'statistiques'
    ],
    'explanation': [
        'explain', 'teach me', 'what is', 'definition',
        'explique', 'apprends-moi', 'qu’est-ce que', 'définition'
    ],
    'outline': [
        'outline', 'plan', 'structure', 'table of contents',
        'plan', 'structure', 'sommaire'
    ],
    'brainstorm': [
        'brainstorm', 'ideas', 'suggest', 'list many',
        'brainstorm', 'idées', 'suggère', 'liste de', 'propose des idées'
    ],
}


CODE_EXTS = {
    '.py', '.js', '.jsx', '.ts', '.tsx', '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.go', '.rs', '.php',
    '.swift', '.kt', '.scala', '.sql', '.sh', '.bash', '.zsh', '.html', '.css', '.scss', '.sass', '.less', '.yaml', '.yml', '.toml', '.ini'
}

DATA_EXTS = {'.csv', '.json', '.jsonl', '.xls', '.xlsx'}
DOC_EXTS = {'.pdf', '.doc', '.docx', '.odt', '.rtf', '.txt', '.md'}


@dataclass
class FileDescriptor:
    filename: str
    mime: Optional[str] = None
    size: Optional[int] = None


def _lower(s: str) -> str:
    return s.lower() if s else ''


def infer_file_category(filename: str, mime: Optional[str] = None) -> str:
    name = filename.lower()
    if mime:
        if 'pdf' in mime:
            return 'pdf'
        if 'json' in mime:
            return 'json'
        if 'csv' in mime:
            return 'csv'
        if 'excel' in mime or 'spreadsheet' in mime:
            return 'spreadsheet'
        if 'text' in mime:
            return 'text'
        if 'image' in mime:
            return 'image'
    # Fallback by extension
    for ext in CODE_EXTS:
        if name.endswith(ext):
            return 'code'
    for ext in DATA_EXTS:
        if name.endswith(ext):
            return 'data'
    for ext in DOC_EXTS:
        if name.endswith(ext):
            return 'document'
    return 'other'


def tokenize_len(s: str) -> int:
    s = s or ''
    return max(0, len(s) // CHARS_PER_TOKEN)


def match_keywords(text: str) -> Dict[str, int]:
    text_l = (text or '').lower()
    scores: Dict[str, int] = {t: 0 for t in TASKS}
    for task, lex in KEYWORDS.items():
        for kw in lex:
            if kw in text_l:
                scores[task] += 1
    # Question mark bonus to QA
    if '?' in text_l:
        scores['question_answering'] += 1
    return scores


def score_from_files(files: List[Dict]) -> Dict[str, int]:
    scores: Dict[str, int] = {t: 0 for t in TASKS}
    for f in files or []:
        fn = f.get('filename') or ''
        cat = infer_file_category(fn, f.get('mime'))
        if cat in ('csv', 'json', 'data', 'spreadsheet'):
            scores['data_analysis'] += 2
            scores['extraction'] += 1
            scores['classification'] += 1
        elif cat in ('pdf', 'document', 'text'):
            # Strong summarization signal; QA shouldn't dominate solely due to '?'
            scores['summarization'] += 4
            scores['extraction'] += 1
        elif cat == 'code':
            scores['code_generation'] += 2
            scores['code_explanation'] += 2
        else:
            # unknown files: mild bias to explanation
            scores['explanation'] += 1
    return scores


def predict_prompt_type(typed_text: str, files: List[Dict]) -> Dict:
    """Predict primary task deterministically from text + file signals."""
    kw_scores = match_keywords(typed_text)
    file_scores = score_from_files(files)

    # Presence signals
    has_text = bool((typed_text or '').strip())
    text_tokens = tokenize_len(typed_text)
    has_files = bool(files)

    # Combine scores
    combined: Dict[str, int] = {t: kw_scores.get(t, 0) + file_scores.get(t, 0) for t in TASKS}

    # Heuristic boosts
    if has_files and not has_text:
        # Pure files — prefer summarization/data/code based on file types
        combined['summarization'] += 2
        combined['data_analysis'] += 1
        combined['code_explanation'] += 1
    if has_text and text_tokens < 10:
        combined['question_answering'] += 1
        combined['brainstorm'] += 1

    # Determine primary task by highest score; tie-break by deterministic order
    ordered_tasks = sorted(TASKS)
    best_task = max(ordered_tasks, key=lambda t: (combined.get(t, 0), t))

    # Override rule: with files present and typed keywords for specific tasks,
    # prefer the override task regardless of summarization/file boosts
    override_applied = None
    if has_files and has_text:
        overrides = [
            (task, kw_scores.get(task, 0), OVERRIDE_PRIORITY.index(task))
            for task in OVERRIDE_PRIORITY
            if kw_scores.get(task, 0) > 0
        ]
        if overrides:
            # Choose by highest keyword hits, then by configured priority
            overrides.sort(key=lambda x: (-x[1], x[2]))
            best_task = overrides[0][0]
            override_applied = best_task

    # Build candidates list sorted by score desc
    candidates = sorted([(t, combined[t]) for t in TASKS if combined[t] > 0], key=lambda x: (-x[1], x[0]))

    reason_parts = []
    if has_text:
        reason_parts.append(f"keywords→{[(t, kw_scores[t]) for t in TASKS if kw_scores[t]>0]}")
    if has_files:
        cats = [infer_file_category(f.get('filename',''), f.get('mime')) for f in files]
        reason_parts.append(f"files→{cats}")
    if override_applied:
        reason_parts.append(f"override→{override_applied}")
    reason = '; '.join(reason_parts) if reason_parts else 'no strong signals'

    return {
        'task_primary': best_task,
        'task_candidates': candidates,
        'signals': {
            'has_text': has_text,
            'text_tokens': text_tokens,
            'has_files': has_files,
            'keyword_scores': kw_scores,
            'file_scores': file_scores,
            'combined_scores': combined,
        },
        'reason': reason,
    }


# Default α, β coefficients per task (heuristic, deterministic)
TASK_COEFFICIENTS: Dict[str, Tuple[float, float]] = {
    # Summarization should not scale too aggressively with P (files-only case especially)
    'summarization': (96.0, 0.03),
    'translation': (32.0, 1.00),
    'rewriting': (32.0, 1.00),
    'question_answering': (64.0, 0.25),
    'extraction': (64.0, 0.08),
    'classification': (32.0, 0.05),
    'sentiment_analysis': (32.0, 0.05),
    'code_generation': (128.0, 0.15),
    'code_explanation': (64.0, 0.14),
    'data_analysis': (64.0, 0.10),
    'explanation': (64.0, 0.20),
    'outline': (64.0, 0.15),
    'brainstorm': (128.0, 0.20),
}


def get_task_coefficients(task: str) -> Tuple[float, float]:
    """Return (alpha, beta) pair for a task; fallback to explanation if unknown."""
    return TASK_COEFFICIENTS.get(task, TASK_COEFFICIENTS['explanation'])
