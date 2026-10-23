#ifndef COINCONTROLDIALOG_H
#define COINCONTROLDIALOG_H

#include <QDialog>

class CCoinControl;
class WalletModel;

QT_BEGIN_NAMESPACE
class QLabel;
class QMenu;
class QPushButton;
class QTreeWidget;
class QTreeWidgetItem;
QT_END_NAMESPACE

/** Pick the exact outputs ("coins") a payment spends, and lock/unlock coins.
 *
 * Edits the CCoinControl it is given in place; SendCoinsDialog passes that
 * to WalletModel::sendCoins. Locked coins are listed but can't be selected
 * until unlocked (right-click).
 */
class CoinControlDialog : public QDialog
{
    Q_OBJECT

public:
    CoinControlDialog(CCoinControl *coinControl, WalletModel *model, QWidget *parent = nullptr);

    enum Column { COLUMN_CHECKBOX, COLUMN_AMOUNT, COLUMN_LABEL, COLUMN_ADDRESS, COLUMN_DATE, COLUMN_CONFIRMATIONS };

private:
    CCoinControl *coinControl;
    WalletModel *model;
    QTreeWidget *tree;
    QLabel *labelSummary;
    QPushButton *selectAllButton;
    QMenu *contextMenu;
    QAction *lockAction;
    QAction *unlockAction;
    QTreeWidgetItem *contextItem;

    void populate();
    void updateSummary();

private slots:
    void itemChanged(QTreeWidgetItem *item, int column);
    void selectAllClicked();
    void showMenu(const QPoint &point);
    void copyAmount();
    void copyAddress();
    void copyTransactionHash();
    void lockCoin();
    void unlockCoin();
};

#endif // COINCONTROLDIALOG_H
