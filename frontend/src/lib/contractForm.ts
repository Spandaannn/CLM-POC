import type {
  Contract,
  ContractCreateRequest,
  ContractStatus,
} from '../api/types'

export interface ContractFormValues {
  title: string
  contract_type: string
  counterparty_name: string
  description: string
  contract_value: string
  currency: string
  start_date: string
  end_date: string
  status: ContractStatus
}

/** Convert a contract from the API into editable form strings. */
export function contractToFormValues(contract: Contract): ContractFormValues {
  return {
    title: contract.title,
    contract_type: contract.contract_type,
    counterparty_name: contract.counterparty_name,
    description: contract.description ?? '',
    contract_value:
      contract.contract_value === null
        ? ''
        : String(contract.contract_value),
    currency: contract.currency,
    start_date: contract.start_date ?? '',
    end_date: contract.end_date ?? '',
    status: contract.status,
  }
}

/** Convert form strings into the JSON shape accepted by the API. */
export function toContractPayload(
  values: ContractFormValues,
): ContractCreateRequest {
  return {
    title: values.title.trim(),
    contract_type: values.contract_type.trim(),
    counterparty_name: values.counterparty_name.trim(),
    description: values.description.trim() || null,
    contract_value: values.contract_value.trim() || null,
    currency: values.currency.trim().toUpperCase(),
    start_date: values.start_date || null,
    end_date: values.end_date || null,
  }
}
