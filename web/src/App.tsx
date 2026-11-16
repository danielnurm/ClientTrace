import { BrowserRouter, Route, Routes } from 'react-router'
import { Check } from './Check'
import { LeadPage } from './LeadPage'
import { Leads } from './Leads'
import { SitePage } from './SitePage'
import { Survey } from './Survey'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Survey />} />
        <Route path="/site/:site" element={<SitePage />} />
        <Route path="/check" element={<Check />} />
        {/* The original sales-lead tool, kept out of the main navigation */}
        <Route path="/leads" element={<Leads />} />
        <Route path="/lead/:site" element={<LeadPage />} />
      </Routes>
    </BrowserRouter>
  )
}
