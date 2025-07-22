self.addEventListener('push', function(event) {
  let data = {};
  try {
    data = event.data.json();
  } catch (e) {
    data = { title: 'Pengingat Minum Obat', body: event.data.text() };
  }
  const title = data.title || 'Pengingat Minum Obat';
  const options = {
    body: data.body || 'Sudah waktunya minum obat!',
    icon: '/static/pill.png', // opsional, bisa diganti
    badge: '/static/pill.png'
  };
  event.waitUntil(self.registration.showNotification(title, options));
}); 