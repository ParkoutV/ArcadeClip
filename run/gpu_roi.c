#define COBJMACROS
#include <windows.h>
#include <d3d11.h>
#include <d3d10.h>
#include <stdlib.h>
#include <string.h>

/* One converter per decoding task. Input textures remain owned by PyAV. */
typedef struct {
    ID3D11Device *device;
    ID3D11DeviceContext *context;
    ID3D11VideoDevice *video;
    ID3D11VideoContext *vc;
    ID3D11VideoProcessorEnumerator *enumerator;
    ID3D11VideoProcessor *processor;
    ID3D11Texture2D *output, *staging, *upload;
    ID3D11VideoProcessorOutputView *view;
    UINT width, height;
} Converter;

#define RELEASE(p) do { if (p) { (p)->lpVtbl->Release(p); (p) = NULL; } } while (0)
__declspec(dllexport) void ac_roi_close(Converter *s) {
    if (!s) return;
    RELEASE(s->view); RELEASE(s->staging); RELEASE(s->output); RELEASE(s->upload);
    RELEASE(s->processor); RELEASE(s->enumerator); RELEASE(s->vc);
    RELEASE(s->video); RELEASE(s->context); RELEASE(s->device);
    free(s);
}
#define CHECK(call) do { hr = (call); if (FAILED(hr)) goto fail; } while (0)

__declspec(dllexport) HRESULT ac_roi_open(ID3D11Texture2D *input, UINT width, UINT height, Converter **result) {
    HRESULT hr = E_FAIL;
    Converter *s = calloc(1, sizeof(*s));
    if (!s) return E_OUTOFMEMORY;
    *result = NULL;
    D3D11_TEXTURE2D_DESC desc;
    ID3D11Texture2D_GetDesc(input, &desc);
    /* Explicitly reject unsupported/high bit depth input rather than changing colors silently. */
    if (desc.Format != DXGI_FORMAT_NV12 || !width || !height) goto fail;
    s->width = width; s->height = height;
    ID3D11Texture2D_GetDevice(input, &s->device);
    ID3D11Device_GetImmediateContext(s->device, &s->context);
    ID3D10Multithread *multithread = NULL;
    CHECK(ID3D11DeviceContext_QueryInterface(s->context, &IID_ID3D10Multithread, (void **)&multithread));
    ID3D10Multithread_SetMultithreadProtected(multithread, TRUE);
    RELEASE(multithread);
    CHECK(ID3D11Device_QueryInterface(s->device, &IID_ID3D11VideoDevice, (void **)&s->video));
    CHECK(ID3D11DeviceContext_QueryInterface(s->context, &IID_ID3D11VideoContext, (void **)&s->vc));
    D3D11_VIDEO_PROCESSOR_CONTENT_DESC content = {0};
    content.InputFrameFormat = D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE;
    content.InputWidth = desc.Width; content.InputHeight = desc.Height;
    content.OutputWidth = width; content.OutputHeight = height;
    content.Usage = D3D11_VIDEO_USAGE_PLAYBACK_NORMAL;
    CHECK(ID3D11VideoDevice_CreateVideoProcessorEnumerator(s->video, &content, &s->enumerator));
    UINT support = 0;
    CHECK(ID3D11VideoProcessorEnumerator_CheckVideoProcessorFormat(s->enumerator, DXGI_FORMAT_B8G8R8A8_UNORM, &support));
    if (!(support & D3D11_VIDEO_PROCESSOR_FORMAT_SUPPORT_OUTPUT)) { hr = E_NOTIMPL; goto fail; }
    CHECK(ID3D11VideoDevice_CreateVideoProcessor(s->video, s->enumerator, 0, &s->processor));
    D3D11_TEXTURE2D_DESC out = {0};
    out.Width = width; out.Height = height; out.MipLevels = 1; out.ArraySize = 1;
    out.Format = DXGI_FORMAT_B8G8R8A8_UNORM; out.SampleDesc.Count = 1;
    out.Usage = D3D11_USAGE_DEFAULT; out.BindFlags = D3D11_BIND_RENDER_TARGET;
    CHECK(ID3D11Device_CreateTexture2D(s->device, &out, NULL, &s->output));
    out.Usage = D3D11_USAGE_STAGING; out.BindFlags = 0; out.CPUAccessFlags = D3D11_CPU_ACCESS_READ;
    CHECK(ID3D11Device_CreateTexture2D(s->device, &out, NULL, &s->staging));
    D3D11_VIDEO_PROCESSOR_OUTPUT_VIEW_DESC vd = {0};
    vd.ViewDimension = D3D11_VPOV_DIMENSION_TEXTURE2D;
    CHECK(ID3D11VideoDevice_CreateVideoProcessorOutputView(s->video, (ID3D11Resource *)s->output,
                                                         s->enumerator, &vd, &s->view));
    *result = s;
    return S_OK;
fail:
    ac_roi_close(s);
    return hr;
}

__declspec(dllexport) HRESULT ac_roi_convert(Converter *s, ID3D11Texture2D *input, UINT slice,
        int left, int top, int matrix709, int full_range, unsigned char *pixels, size_t size) {
    HRESULT hr = E_FAIL;
    ID3D11VideoProcessorInputView *view = NULL;
    if (!s || size < (size_t)s->width * s->height * 4) return E_INVALIDARG;
    D3D11_VIDEO_PROCESSOR_INPUT_VIEW_DESC iv = {0};
    iv.ViewDimension = D3D11_VPIV_DIMENSION_TEXTURE2D; iv.Texture2D.ArraySlice = slice;
    CHECK(ID3D11VideoDevice_CreateVideoProcessorInputView(s->video, (ID3D11Resource *)input,
                                                        s->enumerator, &iv, &view));
    RECT source = {left, top, left + (LONG)s->width, top + (LONG)s->height};
    RECT dest = {0, 0, (LONG)s->width, (LONG)s->height};
    ID3D11VideoContext_VideoProcessorSetStreamFrameFormat(s->vc, s->processor, 0, D3D11_VIDEO_FRAME_FORMAT_PROGRESSIVE);
    ID3D11VideoContext_VideoProcessorSetStreamAutoProcessingMode(s->vc, s->processor, 0, FALSE);
    ID3D11VideoContext_VideoProcessorSetStreamSourceRect(s->vc, s->processor, 0, TRUE, &source);
    ID3D11VideoContext_VideoProcessorSetStreamDestRect(s->vc, s->processor, 0, TRUE, &dest);
    ID3D11VideoContext_VideoProcessorSetOutputTargetRect(s->vc, s->processor, TRUE, &dest);
    D3D11_VIDEO_PROCESSOR_COLOR_SPACE cs = {0};
    cs.YCbCr_Matrix = !!matrix709;
    cs.Nominal_Range = full_range ? D3D11_VIDEO_PROCESSOR_NOMINAL_RANGE_0_255 : D3D11_VIDEO_PROCESSOR_NOMINAL_RANGE_16_235;
    ID3D11VideoContext_VideoProcessorSetStreamColorSpace(s->vc, s->processor, 0, &cs);
    memset(&cs, 0, sizeof(cs)); cs.Nominal_Range = D3D11_VIDEO_PROCESSOR_NOMINAL_RANGE_0_255;
    ID3D11VideoContext_VideoProcessorSetOutputColorSpace(s->vc, s->processor, &cs);
    D3D11_VIDEO_PROCESSOR_STREAM stream = {0};
    stream.Enable = TRUE; stream.pInputSurface = view;
    CHECK(ID3D11VideoContext_VideoProcessorBlt(s->vc, s->processor, s->view, 0, 1, &stream));
    ID3D11DeviceContext_CopyResource(s->context, (ID3D11Resource *)s->staging, (ID3D11Resource *)s->output);
    D3D11_MAPPED_SUBRESOURCE mapped;
    CHECK(ID3D11DeviceContext_Map(s->context, (ID3D11Resource *)s->staging, 0, D3D11_MAP_READ, 0, &mapped));
    for (UINT y = 0; y < s->height; ++y)
        memcpy(pixels + (size_t)y*s->width*4, (char *)mapped.pData + (size_t)y*mapped.RowPitch, (size_t)s->width*4);
    ID3D11DeviceContext_Unmap(s->context, (ID3D11Resource *)s->staging, 0);
fail:
    RELEASE(view);
    return hr;
}

__declspec(dllexport) HRESULT ac_roi_open_cpu(UINT width, UINT height, UINT out_width,
        UINT out_height, Converter **result) {
    HRESULT hr;
    ID3D11Device *device = NULL;
    ID3D11Texture2D *input = NULL;
    *result = NULL;
    CHECK(D3D11CreateDevice(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL,
        D3D11_CREATE_DEVICE_VIDEO_SUPPORT, NULL, 0, D3D11_SDK_VERSION, &device, NULL, NULL));
    D3D11_TEXTURE2D_DESC desc = {0};
    desc.Width = width; desc.Height = height; desc.MipLevels = 1; desc.ArraySize = 1;
    desc.Format = DXGI_FORMAT_NV12; desc.SampleDesc.Count = 1;
    desc.Usage = D3D11_USAGE_DEFAULT; desc.BindFlags = D3D11_BIND_DECODER;
    CHECK(ID3D11Device_CreateTexture2D(device, &desc, NULL, &input));
    CHECK(ac_roi_open(input, out_width, out_height, result));
    (*result)->upload = input;
    input = NULL;
fail:
    RELEASE(input); RELEASE(device);
    return hr;
}

__declspec(dllexport) HRESULT ac_roi_convert_cpu(Converter *s, const void *nv12, UINT pitch,
        int left, int top, int matrix709, int full_range, unsigned char *pixels, size_t size) {
    if (!s || !s->upload || !nv12) return E_INVALIDARG;
    ID3D11DeviceContext_UpdateSubresource(s->context, (ID3D11Resource *)s->upload,
                                        0, NULL, nv12, pitch, 0);
    return ac_roi_convert(s, s->upload, 0, left, top, matrix709, full_range, pixels, size);
}
