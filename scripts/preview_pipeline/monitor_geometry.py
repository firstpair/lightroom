"""Integer sizing intent for a non-upscaled 5120 by2880 display fit.

Inputs must be independently qualified source-encoded crop dimensions. The
orientation maps axes for presentation; it does not rotate image bytes. The
calculation chooses a minimal requested long edge for floor-aspect output.
Actual renderer output, quality, cache identity and native recognition remain
separate evidence. This module neither reads images nor authorizes publication.
"""

SCHEMA='MONITOR_STANDARD_5K_GENERATION_INTENT_V1'
DISPLAY_WIDTH=5120
DISPLAY_HEIGHT=2880
MAX_EDGE=65535
MAX_PIXELS=128000000
ORIENTATIONS=('AB','BC','CD','DA','AD','DC','CB','BA')
SWAPPED_ORIENTATIONS=frozenset(('BC','DA','AD','CB'))


def _need(value,code):
    if not value:raise ValueError('HELD_STANDARD_5K_GEOMETRY_'+code)


def _dimensions(width,height):
    _need(type(width)is int and 1<=width<=MAX_EDGE and
          type(height)is int and 1<=height<=MAX_EDGE,'INTEGER_SOURCE_CROP_DIMENSIONS')
    _need(width*height<=MAX_PIXELS,'SOURCE_CROP_PIXEL_CEILING')


def _ceildiv(numerator,denominator):return (numerator+denominator-1)//denominator


def _oriented(width,height,orientation):
    return (height,width)if orientation in SWAPPED_ORIENTATIONS else(width,height)


def _floor_pair(width,height,preferred):
    return (preferred,(preferred*height)//width)if width>=height else((preferred*width)//height,preferred)


def standard_5k_fit(cropped_width,cropped_height,orientation):
    """Return the smallest preferred long edge covering both rational-fit axes.

    The non-upscaled fit is rounded upward on each required presented axis.
    Inverting the declared floor rule can require a preferred edge one or more
    pixels larger than the display-limited edge. It remains at most the source
    long edge. Actual native returned geometry must be checked independently.
    """
    _dimensions(cropped_width,cropped_height)
    _need(type(orientation)is str and orientation in ORIENTATIONS,'CATALOG_ORIENTATION')
    pw,ph=_oriented(cropped_width,cropped_height,orientation)
    if pw<=DISPLAY_WIDTH and ph<=DISPLAY_HEIGHT:
        required_width,required_height=pw,ph
    elif DISPLAY_WIDTH*ph<=DISPLAY_HEIGHT*pw:
        required_width=DISPLAY_WIDTH
        required_height=_ceildiv(ph*DISPLAY_WIDTH,pw)
    else:
        required_width=_ceildiv(pw*DISPLAY_HEIGHT,ph)
        required_height=DISPLAY_HEIGHT
    required_encoded_width,required_encoded_height=_oriented(required_width,required_height,orientation)
    source_long=max(cropped_width,cropped_height)
    preferred=max(_ceildiv(required_encoded_width*source_long,cropped_width),
                  _ceildiv(required_encoded_height*source_long,cropped_height))
    ew,eh=_floor_pair(cropped_width,cropped_height,preferred)
    presented_width,presented_height=_oriented(ew,eh,orientation)
    _need(1<=preferred<=source_long and 1<=ew<=cropped_width and 1<=eh<=cropped_height,
          'NON_UPSCALED_FLOOR_PAIR')
    _need(presented_width>=required_width and presented_height>=required_height,
          'BOTH_PRESENTED_AXES_COVER_REQUIRED_FIT')
    if preferred>1:
        previous=_oriented(*_floor_pair(cropped_width,cropped_height,preferred-1),orientation)
        _need(previous[0]<required_width or previous[1]<required_height,'MINIMAL_PREFERRED_EDGE')
    return dict(schema=SCHEMA,renderedIntent='STANDARD_5K_FIT',quality='standard',
        orientation=orientation,sourceCroppedWidth=cropped_width,sourceCroppedHeight=cropped_height,
        orientedCroppedWidth=pw,orientedCroppedHeight=ph,
        displayWidth=DISPLAY_WIDTH,displayHeight=DISPLAY_HEIGHT,
        requiredPresentedWidth=required_width,requiredPresentedHeight=required_height,
        preferredSize=preferred,imageLongDimension=source_long,
        normalRenderSizeFlag=preferred==source_long,
        normalRenderSizeFlagScope='PREFERRED_SIZE_EQUALS_QUALIFIED_ENCODED_CROP_LONG_EDGE',
        expectedEncodedWidth=ew,expectedEncodedHeight=eh,
        expectedPresentedWidth=presented_width,expectedPresentedHeight=presented_height,
        sourceResolutionPreserved=preferred==source_long,noFinalRelabel=True,noUpscale=True,
        actualReturnedGeometryRequired=True,nativePyramidSelectionSimulated=False,
        catalogOrientationAppliedToEncodedPixels=False,
        sizingScope='INTEGER_SOURCE_ASPECT_FLOOR_INTENT_NOT_OBSERVED_NATIVE_ARGUMENTS',
        actualLibraryViewportObserved=False,productionPublicationReleased=False,fullRunReleased=False)
