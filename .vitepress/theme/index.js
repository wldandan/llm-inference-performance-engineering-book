import DefaultTheme from 'vitepress/theme'
import { onMounted, watch, nextTick } from 'vue'
import { useRoute } from 'vitepress'
import mediumZoom from 'medium-zoom'
import './custom.css'

export default {
  extends: DefaultTheme,
  setup() {
    const route = useRoute()
    let zoom = null

    // 正文插图点击放大：单实例 + 只绑定新图片（VitePress 是 SPA，翻页后需重挂）
    const attachZoom = () => {
      if (!zoom) {
        zoom = mediumZoom({
          margin: 32,
          background: 'var(--lp-zoom-overlay)',
        })
      }
      const imgs = [
        ...document.querySelectorAll('.vp-doc img:not(.medium-zoom-image)'),
      ].filter((img) => !img.closest('a'))
      if (imgs.length) zoom.attach(imgs)
    }

    onMounted(attachZoom)
    watch(() => route.path, () => nextTick(attachZoom))
  },
}
