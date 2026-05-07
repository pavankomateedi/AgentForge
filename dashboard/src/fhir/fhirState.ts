// Bare context for the FhirClient. JSX-free file so the React-Refresh
// "components-only" rule stays clean on the JSX provider.

import { createContext } from 'react'
import type { FhirClient } from './client'

export const FhirContext = createContext<FhirClient | null>(null)
