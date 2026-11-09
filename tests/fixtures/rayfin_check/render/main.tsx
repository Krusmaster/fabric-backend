// n189: renders the generated App (Rayfin, preview) package's src/App.tsx against fake-connectors.js, outside the
// template's sign-in. ?theme=dark sets the template's `dark` class on <html>, as its useAppTheme does.
import { createRoot } from 'react-dom/client';

import App from '@app/App';

const dark = new URLSearchParams(location.search).get('theme') === 'dark';
document.documentElement.classList.toggle('dark', dark);
document.documentElement.lang = 'en';
document.title = 'Rayfin App check';
createRoot(document.getElementById('root')!).render(<App />);
