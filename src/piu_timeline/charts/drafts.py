"""Persistence preparation for independent, replaceable draft contributions."""
from dataclasses import asdict
from piu_timeline.derived import call
from piu_timeline.charts import ucs


def contribution_id(source):
    return f"{source['source_id']}/segment-{source['segment_number']:03}"


def combine(template, document, metadata, previous=None):
    """An explicit legacy rebuild starts a new baseline; its old bytes remain backed up."""
    source = metadata['source']
    identity = contribution_id(source)
    contributions = [item for item in (previous or {}).get('draft_sources', []) if item['id'] != identity]
    contributions.append({'id': identity, 'source': source, 'document': asdict(document),
                          'combo_analysis': metadata['combo_analysis'], 'alignment': metadata['alignment'],
                          'transcription_alignment': metadata['transcription_alignment'],
                          'placements': metadata['placements'], 'unresolved': metadata['unresolved']})
    metadata['draft_sources'] = contributions
    if len(contributions) == 1:
        metadata['combo_analysis'] = call('chartMerge.comboSummary', asdict(document), metadata['combo_analysis'])
        return document, metadata
    if previous.get('timing_source') != metadata['timing_source']:
        raise ValueError('Cannot merge drafts with different official timing sources')
    merged, proof = call('chartMerge.merge', asdict(template.expanded(document.lanes)),
                         [{k:item[k]for k in ('id','document')}for item in contributions])
    current = call('chartMerge.remap', merged, {k:metadata[k]for k in ('placements','unresolved','summary')})
    metadata.update(current)
    metadata['draft_merge'] = proof
    metadata['transcription'] = proof['transcription']
    metadata['combo_analysis'] = call('chartMerge.comboSummary', merged, metadata['combo_analysis'])
    return ucs.document(merged), metadata
