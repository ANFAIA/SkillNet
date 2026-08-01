import type { Meta } from '@storybook/react-vite'
import { HotspotImageBlock } from './HotspotImageBlock'

const meta: Meta<typeof HotspotImageBlock> = {
  title: 'Courses/Blocks/HotspotImageBlock',
  component: HotspotImageBlock,
  parameters: { a11y: { test: 'error' } },
}
export default meta

export const LayoutTienda = () => (
  <div className="max-w-lg">
    <HotspotImageBlock
      imageUrl="https://placehold.co/800x500/e2e8f0/64748b?text=Plano+de+tienda"
      alt="Plano de la tienda — zonas clave"
      hotspots={[
        { x: 20, y: 30, label: 'Caja principal', detail: 'Aqui se realizan los cobros y devoluciones. Debe haber al menos un empleado en horario de apertura.' },
        { x: 75, y: 25, label: 'Almacen', detail: 'Acceso restringido. Solo personal autorizado. La puerta debe permanecer cerrada.' },
        { x: 50, y: 70, label: 'Zona de probadores', detail: 'Maximo 3 prendas por turno. Revisar el contador al salir el cliente.' },
        { x: 85, y: 80, label: 'Salida de emergencia', detail: 'Debe estar libre de obstaculos en todo momento. Verificar diariamente.' },
      ]}
    />
  </div>
)

export const DosHotspots = () => (
  <div className="max-w-lg">
    <HotspotImageBlock
      imageUrl="https://placehold.co/600x400/e2e8f0/64748b?text=TPV"
      alt="Terminal punto de venta"
      hotspots={[
        { x: 30, y: 50, label: 'Pantalla tactil', detail: 'Interfaz principal de cobro. Tocar el icono de devolucion para iniciar el proceso.' },
        { x: 70, y: 50, label: 'Lector de codigo', detail: 'Escanear el codigo de barras del ticket para localizar la compra original.' },
      ]}
    />
  </div>
)

export const SinHotspots = () => (
  <div className="max-w-lg">
    <HotspotImageBlock
      imageUrl="https://placehold.co/600x400/e2e8f0/64748b?text=Imagen+sin+puntos"
      alt="Imagen de referencia"
      hotspots={[]}
    />
  </div>
)
