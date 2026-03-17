# Design System

> Reference for agents building frontend UI. Based on actual components in `frontend/`.

## Brand Colors

Define your brand palette here. Use semantic names in your component library.

| Token | Hex | Usage |
|-------|-----|-------|
| brand-50 | {{BRAND_50}} | Hover backgrounds (`hover:bg-brand-50`) |
| brand-100 | {{BRAND_100}} | Avatar backgrounds, subtle accents |
| brand-200 | {{BRAND_200}} | Hover borders |
| brand-300 | {{BRAND_300}} | Blockquote borders, dividers |
| brand-500 | {{BRAND_500}} | Focus rings, logo accent |
| brand-600 | {{BRAND_600}} | Primary buttons, links |
| brand-700 | {{BRAND_700}} | Button hover, strong emphasis |

## Gray Scale

| Token | Usage |
|-------|-------|
| gray-50 | Page background |
| gray-100 | Empty state backgrounds, code blocks |
| gray-200 | Card borders, dividers |
| gray-400 | Secondary text, timestamps |
| gray-500 | Descriptions, sub-labels |
| gray-600 | Body text, cancel buttons |
| gray-700 | Field values, nav items |
| gray-900 | Headings, primary text |

## Status Colors

| Status | Badge BG | Badge Text | Dot |
|--------|----------|------------|-----|
| active / success | `bg-green-50` | `text-green-700` | `bg-green-500` |
| warning / pending | `bg-yellow-50` | `text-yellow-700` | `bg-yellow-500` |
| inactive / paused | `bg-gray-50` | `text-gray-600` | `bg-gray-400` |
| error / failed | `bg-red-50` | `text-red-700` | `bg-red-500` |

## Typography

- **Font**: {{PRIMARY_FONT}} (sans-serif)
- **Monospace**: {{MONO_FONT}} for code blocks
- **Page titles**: text-2xl font-bold
- **Section headings**: text-lg font-semibold
- **Card titles**: font-semibold text-sm
- **Labels**: text-xs text-gray-500
- **Body**: text-sm text-gray-600

## Component Patterns

- **Cards**: rounded border with padding. Add hover shadow when clickable.
- **Stat cards**: label/value/sub structure in a bordered container.
- **Badges**: inline-flex with colored dot and ring.
- **Primary button**: brand-colored background, white text, rounded, hover state.
- **Form inputs**: bordered, rounded, focus ring in brand color.
- **Error banners**: red background, red border, red text.
- **Breadcrumbs**: gray text links with separator, current page darker.

## Spacing

- Page padding: 2rem (p-8)
- Content max-width: varies by page type (list: 64rem, detail: 56rem, form: 48rem)
- Section gap: 2rem (mb-8)
- Card grid: responsive columns with 1rem gap
- Form field spacing: 1rem inside card, 1.5rem between sections

## Layout

- Sidebar: fixed width, white background, bordered right edge, logo + nav + footer
- Main content: flex-1, scrollable
- Nav items: padded, rounded, with icon + label
