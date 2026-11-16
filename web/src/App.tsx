import { BrowserRouter, Route, Routes } from 'react-router'
import { SitePage } from './SitePage'
import { Survey } from './Survey'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Survey />} />
        <Route path="/site/:site" element={<SitePage />} />
      </Routes>
    </BrowserRouter>
  )
}
