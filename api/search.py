import operator
import re
from functools import reduce

from django.db.models import Case, IntegerField, Q, Value, When

from .models import KBEntry

STOPWORDS = {
    'a', 'an', 'and', 'are', 'be', 'can', 'do', 'does', 'for', 'how', 'i',
    'in', 'is', 'it', 'my', 'no', 'not', 'of', 'on', 'or', 'should', 'the',
    'to', 'use', 'using', 'what', 'when', 'where', 'which', 'why', 'with',
}
MAX_TERMS = 10


def normalize(search):
    """Canonical form stored in QueryLog so 'JWT' and ' jwt ' count as one term."""
    return ' '.join(search.lower().split())


def extract_terms(search):
    """Split a search into keywords, dropping stopwords and duplicates.

    Falls back to the whole phrase when nothing is left (e.g. "how to").
    """
    terms = []
    for token in re.findall(r'[\w.()-]+', search.lower()):
        token = token.strip('.-')
        if len(token) > 1 and token not in STOPWORDS and token not in terms:
            terms.append(token)
    return terms[:MAX_TERMS] or [normalize(search)]


def search_kb(search):
    """KB entries matching any keyword in question or answer, best matches first.

    relevance = keywords matched anywhere + keywords matched in the question.
    """
    matches = []
    score = []
    for term in extract_terms(search):
        in_question = Q(question__icontains=term)
        in_either = in_question | Q(answer__icontains=term)
        matches.append(in_either)
        score.append(Case(When(in_either, then=Value(1)), default=Value(0), output_field=IntegerField()))
        score.append(Case(When(in_question, then=Value(1)), default=Value(0), output_field=IntegerField()))

    return (
        KBEntry.objects
        .filter(reduce(operator.or_, matches))
        .annotate(relevance=reduce(operator.add, score))
        .order_by('-relevance', 'id')
    )
