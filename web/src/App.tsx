import { BrowserRouter, Route, Routes } from 'react-router'
import { LeadPage } from './LeadPage'
import { Leads } from './Leads'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Leads />} />
        <Route path="/lead/:site" element={<LeadPage />} />
      </Routes>
    </BrowserRouter>
  )
}
