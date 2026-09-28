import urllib.request
try:
    r = urllib.request.urlopen('http://127.0.0.1:5000/caregiver-login')
    html = r.read().decode('utf-8')
    print('Status:', r.status)
    print('Caregivers listed:', html.count('caregiver_'))
except Exception as e:
    print('Error:', e)
