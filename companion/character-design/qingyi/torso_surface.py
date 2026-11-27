"""Finish the chest surface and the transition from upper arm to rib cage."""
import numpy as np
from scipy.interpolate import LinearNDInterpolator, RectBivariateSpline
from scipy.ndimage import gaussian_filter, distance_transform_edt
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import splu

from yuexiao_torso import centre, radius, smooth


def unit(v):
    return v/np.maximum(np.linalg.norm(v,axis=1,keepdims=True),1e-12)


def chest_surface(points, donor, rise, old_normals):
    h=points[:,1]-rise
    c=centre(np.clip(h,12.9,18.5))
    x,_,z=points.T
    angle=np.arctan2(x,c-z)
    radial=np.hypot(x,c-z)
    da=np.arctan2(donor[:,0],c-donor[:,2])
    residual=np.hypot(donor[:,0],c-donor[:,2])-radius(da,np.clip(h,12.9,18.5))
    # At the axilla an angular ray can meet both the ribs and the upper
    # arm. Use the inner skin chart to fit the torso, keeping the outer arm
    # chart available for the separately smoothed skin-weight transition.
    core=(h>14.75)&(h<18.10)&(abs(angle)<2.78)&(abs(x)<2.0)
    core&=(abs(da)<1.22)|(residual<.19)
    levels=np.linspace(14.86,18.02,211)
    angles=np.linspace(0,2.65,213)
    aa,hh=np.meshgrid(angles,levels)
    sides=[]
    for sign in (-1,1):
        use=core&(sign*x>=-.0005)
        interpolator=LinearNDInterpolator(np.c_[abs(angle[use]),h[use]],radial[use])
        s=interpolator(aa,hh)
        absent=~np.isfinite(s)
        nearest=distance_transform_edt(absent,return_distances=False,return_indices=True)
        sides.append(s[tuple(nearest)])
    # Regularize in physical angular/vertical distance. Reflect at the
    # midsagittal plane to give the two sides the same tangents at the seam.
    target=(sides[0]+sides[1])*.5
    target=gaussian_filter(target,(10.0,8.3),mode=('nearest','reflect'))
    # Round the lower pole under each breast. Under the sternum and near the
    # outside rib the lower edge turns up earlier, so the shadow follows a
    # pair of shallow arcs rather than a level shelf across the torso.
    def paired_arc(at,spread):
        return np.exp(-((aa-at)/spread)**2)+np.exp(-((aa+at)/spread)**2)
    pole=paired_arc(.52,.37)
    lower=np.exp(-((hh-16.02)/.38)**2)
    medial=np.exp(-(aa/.27)**2)
    outer=paired_arc(1.12,.32)
    target+=lower*(.092*pole-.061*medial-.051*outer)
    target+=np.exp(-((hh-16.64)/.69)**2)*(.037*pole-.038*medial)
    sheet=RectBivariateSpline(levels,angles,target)
    hq=np.clip(h,levels[0],levels[-1])
    aq=np.clip(abs(angle),0,angles[-1])
    fitted=sheet.ev(hq,aq)
    front=smooth((h-15.00)/.45)*smooth((17.97-h)/.41)
    arm_distance=smooth((.43-residual)/.26)
    trunk=1-smooth((abs(da)-1.08)/.43)*(1-arm_distance)
    # The upper arm root doubles back over the same ray. Keep its topology
    # intact and fair that concave fold along the mesh instead of flattening it.
    arm_root=smooth((h-16.42)/.42)*smooth((abs(angle)-1.12)/.41)
    weight=front*smooth((2.60-abs(angle))/.57)*trunk*smooth((2.08-abs(x))/.39)*(1-arm_root)
    offset=(fitted-radial)*weight
    new=points.copy()
    new[:,0]+=offset*np.sin(angle)
    new[:,2]-=offset*np.cos(angle)
    # Differentiate the same surface used for the vertices. A sewn UV
    # boundary therefore cannot introduce a separate highlight.
    sa,ca=np.sin(angle),np.cos(angle)
    ds=sheet.ev(hq,aq,dy=1)*np.sign(angle)
    dh=sheet.ev(hq,aq,dx=1)
    ta=np.c_[ds*sa+fitted*ca,np.zeros_like(h),-ds*ca+fitted*sa]
    th=np.c_[dh*sa,np.ones_like(h),centre.derivative()(np.clip(h,12.9,18.5))-dh*ca]
    normals=unit((1-weight[:,None])*old_normals+weight[:,None]*unit(np.cross(th,ta)))
    return new,normals


def surface_laplacian(points,faces):
    vertices=points[faces]
    double_area=np.linalg.norm(np.cross(vertices[:,1]-vertices[:,0],
                                        vertices[:,2]-vertices[:,0]),axis=1)
    mass=np.bincount(faces.ravel(),np.repeat(double_area/6,3),minlength=len(points))
    edges=[];coeff=[]
    for k in range(3):
        i,j=(k+1)%3,(k+2)%3
        cot=((vertices[:,i]-vertices[:,k])*(vertices[:,j]-vertices[:,k])).sum(axis=1)
        coeff.append(.5*cot/np.maximum(double_area,1e-12))
        edges.append(faces[:,[i,j]])
    ei,ej=np.concatenate(edges).T
    adj=coo_matrix((np.concatenate(coeff),(ei,ej)),shape=(len(points),len(points))).tocsr()
    adj=adj+adj.T
    adj.data=np.clip(adj.data,0,75)
    return mass,diags(np.asarray(adj.sum(axis=1)).ravel())-adj


def diffuse(values,fade,mass,lap,dt,passes):
    inside=np.flatnonzero(fade>0)
    outside=np.flatnonzero(fade==0)
    m=mass[inside].clip(1e-8)
    solve=splu((diags(m)+dt*lap[inside][:,inside]).tocsc())
    fixed=lap[inside][:,outside]
    active=(abs(values[inside]).max(axis=0)>0)|(abs(fixed@values[outside]).max(axis=0)>0)
    local=np.flatnonzero(active)
    boundary=-dt*(fixed@values[np.ix_(outside,local)])
    mixed=values[np.ix_(inside,local)]
    for _ in range(passes):
        mixed=solve.solve(m[:,None]*mixed+boundary)
    result=values.copy()
    result[np.ix_(inside,local)]+=fade[inside,None]*(mixed-values[np.ix_(inside,local)])
    return result


def fair_axilla(points,normals,rise,faces):
    x,y,z=points.T
    h=y-rise
    fade=(smooth((abs(x)-.84)/.35)*smooth((2.47-abs(x))/.44)*
          smooth((h-15.49)/.54)*smooth((18.02-h)/.48)*
          smooth((z+.84)/.47)*smooth((1.57-z)/.46))
    mass,lap=surface_laplacian(points,faces)
    # Diffuse on the sewn surface, not in a Euclidean point cloud; an arm
    # and a rib can be close without sharing their tangents or their weights.
    points=diffuse(points,fade,mass,lap,.008,2)
    tri=points[faces]
    area=np.cross(tri[:,2]-tri[:,0],tri[:,1]-tri[:,0])
    geometric=np.zeros_like(points)
    for corner in faces.T:np.add.at(geometric,corner,area)
    mass,lap=surface_laplacian(points,faces)
    soft=unit(diffuse(unit(geometric),fade,mass,lap,.006,2))
    return points,unit(normals+(soft-normals)*fade[:,None]),mass,lap,fade


def axilla_weights(donor,points,rise,first,merge,mass,lap):
    x,y,z=points.T
    h=y-rise
    fade=(smooth((abs(x)-.68)/.36)*smooth((2.82-abs(x))/.48)*
          smooth((h-15.42)/.54)*smooth((18.32-h)/.54)*
          smooth((z+1.09)/.55)*smooth((1.74-z)/.48))
    bones=donor['bones'][first]
    weights=donor['weights'][first]
    active=np.unique(bones[weights>0])
    dense=np.zeros((len(points),len(active)))
    rows,cols=np.nonzero(weights>0)
    np.add.at(dense,(rows,np.searchsorted(active,bones[rows,cols])),weights[rows,cols])
    dense=diffuse(dense,fade,mass,lap,.0225,3)
    dense[dense<1.e-8]=0
    dense/=dense.sum(axis=1,keepdims=True)
    # Blender supports more than four influences. Discarding the fifth at
    # the deltoid/torso transition reintroduces the original weight steps.
    slots=np.count_nonzero(dense,axis=1).max()
    order=np.argsort(-dense,axis=1,kind='stable')[:,:slots]
    return active[order][merge],np.take_along_axis(dense,order,axis=1)[merge]


def finish_skin(donor,shapes):
    original=shapes['sculpt']
    original_normals=shapes['sculpt_normals']
    _,first,merge=np.unique(donor['coords'].round(5),axis=0,return_index=True,return_inverse=True)
    points,normals=chest_surface(original[first],donor['coords'][first],
                                 donor['rise'],original_normals[first])
    points,normals,mass,lap,fade=fair_axilla(points,normals,donor['rise'],merge[donor['faces']])
    donor['axilla_fade']=fade[merge]
    bones,weights=axilla_weights(donor,points,donor['rise'],first,merge,mass,lap)
    donor['previous_bones'],donor['previous_weights']=donor['bones'],donor['weights']
    donor['bones'],donor['weights']=bones,weights
    shapes.update(previous=original,previous_normals=original_normals,
                  sculpt=points[merge],
                  sculpt_normals=unit(original_normals+(normals-original_normals[first])[merge]))
