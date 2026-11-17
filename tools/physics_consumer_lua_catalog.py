"""Emit byte-exact consumer catalogs within Chef's 4 MiB Lua resource cap.

Only representation is changed: identical binary evidence is interned and stored as
ASCII base64, decoded once at module load without bit/ffi or per-frame work.
"""
import base64
import json
import math

DECODE = r'''local function decode(s)
 local alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
 local value={};for i=1,#alphabet do value[alphabet:byte(i)]=i-1 end
 assert(#s%4==0,"consumer base64 length")
 local out={}
 for i=1,#s,4 do
  local a,b,c,d=s:byte(i,i+3)
  local x,y,z,w=value[a],value[b],value[c],value[d]
  assert(x and y and (z or c==61) and (w or d==61),"consumer base64 alphabet")
  assert(z or d==61,"consumer base64 padding")
  assert((z and w)or i+3==#s,"consumer base64 padding position")
  local n=x*262144+y*4096+(z or 0)*64+(w or 0)
  local bytes=string.char(math.floor(n/65536),math.floor(n/256)%256,n%256)
  if not z then assert(y%16==0,"consumer base64 trailing bits");bytes=bytes:sub(1,1)
  elseif not w then assert(z%4==0,"consumer base64 trailing bits");bytes=bytes:sub(1,2)end
  out[#out+1]=bytes
 end
 return table.concat(out)
end'''


def emit_catalog(catalog):
    blobs = []
    indices = {}

    def emit(v):
        if v is None: return 'nil'
        if v is True: return 'true'
        if v is False: return 'false'
        if isinstance(v, (float, int)):
            if not math.isfinite(v): raise ValueError('non-finite catalog number')
            return repr(v)
        if isinstance(v, str): return json.dumps(v, ensure_ascii=False)
        if isinstance(v, list): return '{' + ','.join(map(emit, v)) + '}'
        if isinstance(v, dict):
            fields = []
            for key, value in sorted(v.items()):
                if key.endswith('ExactBase64'):
                    raw = base64.b64decode(value, validate=True)
                    if raw not in indices:
                        indices[raw] = len(blobs) + 1
                        blobs.append(base64.b64encode(raw).decode('ascii'))
                    fields.append('[' + emit(key[:-6]) + ']=blobs[' + str(indices[raw]) + ']')
                else:
                    fields.append('[' + emit(key) + ']=' + emit(value))
            return '{' + ','.join(fields) + '}'
        raise TypeError(type(v))

    body = emit(catalog)
    pool = '{' + ','.join(json.dumps(b) for b in blobs) + '}'
    text = '(function()\n' + DECODE + '\nlocal blobs=' + pool + '\nfor i,s in ipairs(blobs)do blobs[i]=decode(s)end\nreturn ' + body + '\nend)()'
    return text, dict(uniqueBlobs=len(blobs), uniqueRawBytes=sum(map(len, indices)), encodedBytes=sum(map(len, blobs)))
