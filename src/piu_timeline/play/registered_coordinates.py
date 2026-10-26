"""Jointly register identified heads without accumulating peer-turnover bias."""
from collections import defaultdict

import numpy as np

FORMAT={'schema':1,'revision':1,'model':'head_y_plus_frame_displacement_equals_head_offset',
        'robust_passes':3,'maximum_iterations':512,'gradient_tolerance':1e-5,'huber_pixels':1.5}


def solve(head,frame,y,initial,head_count,frame_count):
    """Eliminate frame offsets and solve the head-overlap Laplacian matrix-free."""
    weights=np.ones(len(y));offsets=None;iterations=0
    if not np.isfinite(y).all():raise ValueError('nonfinite_registered_positions')
    for _ in range(FORMAT['robust_passes']):
        degree=np.bincount(head,weights=weights,minlength=head_count)
        total=np.bincount(frame,weights=weights,minlength=frame_count)
        if (degree<=0).any() or (total<=0).any():raise ValueError('unobserved_joint_coordinate')
        mean_y=np.bincount(frame,weights=weights*y,minlength=frame_count)/total
        rhs=np.bincount(head,weights=weights*(y-mean_y[frame]),minlength=head_count)
        rhs-=rhs.mean()
        diagonal=degree-np.bincount(head,weights=weights**2/total[frame],minlength=head_count)
        def product(values):
            means=np.bincount(frame,weights=weights*values[head],minlength=frame_count)/total
            return degree*values-np.bincount(head,weights=weights*means[frame],minlength=head_count)
        if offsets is None:
            offsets=np.bincount(head,weights=weights*(y+initial[frame]),minlength=head_count)/degree
        offsets-=offsets.mean()
        residual=rhs-product(offsets);scaled=residual/np.maximum(diagonal,1e-9)
        direction=scaled.copy();error=float(np.dot(residual,scaled))
        for _ in range(FORMAT['maximum_iterations']):
            if np.sqrt(max(0,error))<FORMAT['gradient_tolerance']:break
            projected=product(direction);denominator=float(np.dot(direction,projected))
            if denominator<=1e-20:break
            step=error/denominator;offsets+=step*direction;residual-=step*projected
            scaled=residual/np.maximum(diagonal,1e-9);updated=float(np.dot(residual,scaled))
            direction=scaled+(updated/error)*direction;error=updated;iterations+=1
        if not np.isfinite(offsets).all() or np.sqrt(max(0,error))>=FORMAT['gradient_tolerance']:
            raise ValueError('joint_coordinate_solver_not_converged')
        phase=np.bincount(frame,weights=weights*(offsets[head]-y),minlength=frame_count)/total
        errors=offsets[head]-phase[frame]-y
        weights=np.minimum(1,FORMAT['huber_pixels']/np.maximum(abs(errors),1e-6))
    origin=phase[0]
    return phase-origin,offsets-origin,iterations


def refine(motion,tracks,receptor,spacing,bottom):
    """Change derived displacement only; retain original head positions and PTS."""
    positions=defaultdict(dict)
    for index,track in enumerate(tracks):
        for time,y in track.points:
            if receptor+.85*spacing<y<bottom-.55*spacing:positions[time][index]=y
    motion.coordinate_failures={};motion.coordinate_conflicts=[];motion.coordinate_offsets={};diagnostics=[]
    for chunk_number,chunk in enumerate(motion.chunks):
        if len(chunk)<4:continue
        identities=sorted({i for sample in chunk for i in positions[sample['time']]})
        if len(identities)<2:continue
        mapping={index:i for i,index in enumerate(identities)};heads=[];frames=[];ys=[]
        parents=list(range(len(identities)))
        def root(i):
            while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
            return i
        for frame,sample in enumerate(chunk):
            indices=list(positions[sample['time']])
            for index in indices:
                heads.append(mapping[index]);frames.append(frame);ys.append(positions[sample['time']][index])
                parents[root(mapping[index])]=root(mapping[indices[0]])
        record={'chunk':chunk_number,'frames':len(chunk),'heads':len(identities),
                'source_pts_seconds':[chunk[0]['source_pts'],chunk[-1]['source_pts']]}
        try:
            if len(set(root(i) for i in range(len(identities))))!=1:
                raise ValueError('disconnected_registered_identities')
            head,frame,y=np.asarray(heads),np.asarray(frames),np.asarray(ys)
            phase,offsets,iterations=solve(head,frame,y,np.array([s['phase']for s in chunk]),len(identities),len(chunk))
            forward=np.maximum.accumulate(phase)
            if max(forward-phase)>max(.75,.02*spacing):
                raise ValueError('joint_coordinates_contradict_forward_motion')
            errors=offsets[head]-forward[frame]-y
            record.update(status='fitted',iterations=iterations,residual_pixels=float(np.sqrt(np.mean(errors**2))),
                          maximum_residual_pixels=float(max(abs(errors))),
                          maximum_forward_adjustment_pixels=float(max(forward-phase)),
                          maximum_phase_correction_pixels=float(max(abs(forward-np.array([s['phase']for s in chunk])))))
            for i,index in enumerate(identities):motion.coordinate_offsets[(id(tracks[index]),chunk_number)]=float(offsets[i])
            record['head_offsets']=[{'note':index,'offset_pixels':float(offsets[i])} for i,index in enumerate(identities)]
            for sample,value in zip(chunk,forward,strict=True):
                sample.update(phase=float(value),coordinate_status='joint_registered')
            # Robust weighting is inference, not deletion of inconvenient source
            # observations. Expose every point outside the existing fit gate.
            for local,index in enumerate(identities):
                bad=np.flatnonzero((head==local)&(abs(errors)>.15*spacing))
                if not len(bad):continue
                times=[chunk[frame[i]]['time']for i in bad]
                motion.coordinate_conflicts.append({'note':index,'lane':tracks[index].lane,
                    'reason':'shared_motion_observation_conflict','check':'timing_reconstruction',
                    'visible_start_seconds':min(times),'visible_end_seconds':max(times),
                    'source_pts_seconds':[chunk[frame[bad[0]]]['source_pts'],chunk[frame[bad[-1]]]['source_pts']],
                    'observed_points':len(bad),'maximum_position_error_pixels':float(max(abs(errors[bad]))),
                    'position_tolerance_pixels':.15*spacing,'motion_chunk':chunk_number})
        except ValueError as error:
            record.update(status='failed',reason=str(error));motion.coordinate_failures[chunk_number]=str(error)
            for sample in chunk:sample['coordinate_status']='failed'
        diagnostics.append(record)
    motion.clocks={}
    motion.coordinate_registration={'format':FORMAT,'chunks':diagnostics}
