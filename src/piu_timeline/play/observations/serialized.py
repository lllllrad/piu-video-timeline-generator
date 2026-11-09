"""File-reference lookup before constructing a native measurement request."""
import json

from piu_timeline.play.observations.artifacts import file_identities,save_input,producer as implementation
from piu_timeline.play.stages import fingerprint,paths


def reuse(directory,name,dependencies,parameters,producer,compute):
    """Dependency files own the values; parameters contain only unsaved settings."""
    binding={'inputs':file_identities(directory,dependencies),'parameters':parameters,'producer':producer,
             'storage':implementation('play/observations/serialized.py')}
    digest=fingerprint(binding);receipt=directory/'native-stages'/f'{name}.stage.json'
    output=directory/'native-stages'/f'{name}.json'
    if receipt.is_file():
        saved=json.loads(receipt.read_text())
        if saved.get('schema')!=1 or saved.get('stage')!=name:raise ValueError('Invalid serialized native stage')
        if saved['binding_fingerprint']==digest:
            if saved['artifact']!=file_identities(directory,(str(output.relative_to(directory)),)):
                raise ValueError('Corrupt serialized native output')
            artifact=json.loads(output.read_text())
            if artifact.get('stage')!=name or artifact.get('schema')!=1:raise ValueError('Invalid serialized native output')
            return paths(artifact['output'],'@segment/',str(directory.resolve())+'/')
    result=compute()
    if binding['inputs']!=file_identities(directory,dependencies):raise ValueError('Serialized native inputs changed during calculation')
    save_input(receipt,{'schema':1,'stage':name,'binding_fingerprint':digest,
                       'inputs':binding['inputs'],'parameters':parameters,'producer':producer,
                       'artifact':file_identities(directory,(str(output.relative_to(directory)),))})
    return result
