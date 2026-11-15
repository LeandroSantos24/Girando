// <image-slot> de solo lectura para producción.
// Reemplaza al image-slot del prototipo (que permitía arrastrar fotos y las guardaba en el navegador).
// Muestra la imagen del atributo `src` (URL generada por el backend) o un marcador neutro.
(function () {
  if (customElements.get('image-slot')) return;
  const SAFE = /^(\/media\/[A-Za-z0-9/_\-.]+|https:\/\/res\.cloudinary\.com\/[A-Za-z0-9/_\-.,:]+)$/;
  class ImageSlot extends HTMLElement {
    static get observedAttributes() { return ['src', 'placeholder', 'shape', 'radius', 'alt']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.isConnected) this.render(); }
    render() {
      const src = this.getAttribute('src') || '';
      const shape = this.getAttribute('shape') || 'rect';
      // shape="css": el radio lo define la hoja de estilos (cards responsive)
      const radius = shape === 'css' ? null : shape === 'circle' ? '50%' : shape === 'rounded' ? (this.getAttribute('radius') || '8') + 'px' : '0';
      this.style.display = this.style.display || 'block';
      this.style.overflow = 'hidden';
      if (radius !== null) this.style.borderRadius = radius;
      this.style.background = this.style.background || 'var(--color-neutral-200, #eef1f5)';
      this.style.position = this.style.position || 'relative';
      this.textContent = '';
      if (src && SAFE.test(src)) {
        const img = document.createElement('img');
        img.src = src; img.loading = 'lazy'; img.decoding = 'async';
        img.alt = this.getAttribute('alt') || '';
        img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
        this.appendChild(img);
      } else {
        const ph = document.createElement('span');
        ph.textContent = this.getAttribute('placeholder') || '';
        ph.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;text-align:center;padding:4px;font:600 11px/1.3 Sora,sans-serif;color:#8a909b;';
        this.appendChild(ph);
      }
    }
  }
  customElements.define('image-slot', ImageSlot);
})();

// <yt-embed video="ID">: crea el iframe de YouTube (sin cookies) recién cuando hay un ID válido.
// Evita que la plantilla dispare una carga con el texto literal {{ … }} antes de enlazar los datos.
(function () {
  if (customElements.get('yt-embed')) return;
  const ID = /^[A-Za-z0-9_-]{6,20}$/;
  class YtEmbed extends HTMLElement {
    static get observedAttributes() { return ['video']; }
    connectedCallback() { this.render(); }
    attributeChangedCallback() { if (this.isConnected) this.render(); }
    render() {
      const id = this.getAttribute('video') || '';
      this.textContent = '';
      if (!ID.test(id)) return;
      const f = document.createElement('iframe');
      f.src = 'https://www.youtube-nocookie.com/embed/' + id;
      f.title = 'Video de YouTube';
      f.allowFullscreen = true;
      f.loading = 'lazy';
      f.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;border:0;';
      this.appendChild(f);
    }
  }
  customElements.define('yt-embed', YtEmbed);
})();
