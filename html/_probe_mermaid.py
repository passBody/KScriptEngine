import urllib.request, json, io, tarfile, sys, os

BASE = 'https://mirror.zlg.com'
REPOS = ['npm-group','npm-proxy','npm-public','npmjs-proxy','npmjs','npm','npm-registry','npm-repos']
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mermaid.min.js')

def get(url, timeout=30, headers=None):
    h = {'User-Agent': 'Mozilla/5.0'}
    if headers: h.update(headers)
    return urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout).read()

meta = None
repo = None
for r in REPOS:
    u = f'{BASE}/repository/{r}/mermaid'
    try:
        data = get(u, 25, {'Accept': 'application/vnd.npm.install-v1+json'})
        if b'dist-tags' in data or b'tarball' in data:
            meta = data; repo = r; print('META_OK', r, len(data)); break
        print('META_NONJSON', r, data[:60])
    except Exception as e:
        print('META_FAIL', r, type(e).__name__, str(e)[:70])

if not meta:
    print('NO_NPM_MIRROR_FOUND'); sys.exit(0)

j = json.loads(meta)
latest = (j.get('dist-tags') or {}).get('latest')
print('latest =', latest)
ver = latest or '11.11.0'
try:
    tb = j['versions'][ver]['dist']['tarball']
except (KeyError, TypeError):
    tb = None
if not tb or not tb.startswith(BASE):
    tb = f'{BASE}/repository/{repo}/mermaid/-/mermaid-{ver}.tgz'
    print('rewrote tarball ->', tb)
else:
    print('tarball ->', tb)

try:
    tgz = get(tb, 60)
except Exception as e:
    print('TARBALL_FAIL', type(e).__name__, str(e)[:90]); sys.exit(0)
print('tgz bytes =', len(tgz))

tf = tarfile.open(fileobj=io.BytesIO(tgz), mode='r:gz')
target = None
for m in tf.getmembers():
    if m.name.endswith('dist/mermaid.min.js'):
        target = m; break
if target:
    f = tf.extractfile(target).read()
    open(OUT, 'wb').write(f)
    print('EXTRACTED_OK', len(f), '->', OUT)
else:
    cands = [m.name for m in tf.getmembers() if m.name.endswith('.min.js')]
    print('NO_TARGET_IN_TGZ; .min.js entries:', cands[:8])
