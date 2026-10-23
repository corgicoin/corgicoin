// Copyright (c) 2011-2013 The Bitcoin developers
// Copyright (c) 2014-2026 Corgicoin Developers
// Distributed under the MIT/X11 software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef COINCONTROL_H
#define COINCONTROL_H

#include <set>
#include <variant>
#include <vector>

#include "main.h"   // COutPoint
#include "script.h" // CTxDestination

/** User-chosen inputs and change destination for CWallet::CreateTransaction.
 *
 * When any outputs are selected, the transaction spends exactly those (all
 * of them) instead of running automatic coin selection. A destChange other
 * than CNoDestination replaces the fresh keypool change address.
 */
class CCoinControl
{
public:
    CTxDestination destChange = CNoDestination();

    void SetNull()
    {
        destChange = CNoDestination();
        setSelected.clear();
    }

    bool HasSelected() const { return !setSelected.empty(); }
    bool HasCustomChange() const { return !std::holds_alternative<CNoDestination>(destChange); }

    bool IsSelected(const uint256& hash, unsigned int n) const
    {
        return setSelected.count(COutPoint(hash, n)) > 0;
    }

    void Select(const COutPoint& output) { setSelected.insert(output); }
    void UnSelect(const COutPoint& output) { setSelected.erase(output); }
    void UnSelectAll() { setSelected.clear(); }

    void ListSelected(std::vector<COutPoint>& vOutpoints) const
    {
        vOutpoints.assign(setSelected.begin(), setSelected.end());
    }

private:
    std::set<COutPoint> setSelected;
};

#endif // COINCONTROL_H
